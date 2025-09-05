import asyncio
import json
from math import floor
import time
import traceback
import uuid
import logging
import asyncio
from typing import Callable, Coroutine, Literal
from pathlib import Path

from websockets.asyncio.server import Server, ServerConnection
from websockets import ConnectionClosed

from src.config import Config
from src.compressor import Compressor
from src.memory import Memory
from src.ai import AI
from src.messages import MessageTypes, MsgClose, MsgEvict, MsgQuery, MsgStore, MsgProcess
from src.db_bundle import DbBundle


class WssHandler:
    config: Config
    env: dict

    dbs: DbBundle
    ai: AI
    logger: logging.Logger

    server: Server = None
    close_server: asyncio.Future

    handlers: dict[MessageTypes, Callable[[ServerConnection, dict], Coroutine]]
    consecutive_err_count: dict[str, int]
    recv_time: int = 0


    def __init__(self, database_bundle: DbBundle, config: Config, env: dict)-> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.config = config
        self.env = env
        
        self.dbs = database_bundle
        self.handlers = {
            "query": self._on_query,
            "store": self._on_store,
            "process": self._on_process,
            "evict": self._on_evict,
            "clear": self._on_clear,
            "close": self._on_close,
            "unhandled": self._on_unhandled,
        }
        self.consecutive_err_count = {
            "send": 0
        }

        self.ai = AI(
            base_url=config.openllm.base_url,
            model_name=config.openllm.model,
            api_key=env["OPENAI_API_KEY"],
            config=config
        )
        self.compressor = Compressor(ai=self.ai, long_vdb=self.dbs.long_term, config=self.config)

        self._compress_q: asyncio.Queue[tuple[str, list[Memory]]] = asyncio.Queue(maxsize=8)
        self._compress_worker_task = asyncio.create_task(self._compressor_worker())

        self.dbs.short_term.set_on_evict(self._on_evict_chunk)
        self.logger.info("initialized wss handler")
        return


    async def bind_and_wait(self, server: Server)-> None:
        self.server = server
        self.close_server = asyncio.Future()
        await self.close_server


    async def _send(self, conn: ServerConnection, data: dict)-> None:
        try:
            json_data = json.dumps(data)
            await conn.send(json_data, text=True)
            self.logger.info("recv->send latency: %d", int(time.time() * 1_000) - self.recv_time)
            self.logger.info("sent: %s", json_data)
            self.consecutive_err_count["send"] = 0

        except ConnectionClosed as e:
            raise e
        
        except Exception as e:
            # should not be able to be thrown, would trigger inifine loop
            # since we are using _send_error in the exception handling
            self.logger.error("error during sending: %s\n%s", str(e), traceback.format_exc())
            self.consecutive_err_count["send"] = self.consecutive_err_count.get("send", 0) + 1

            if self.consecutive_err_count.get("send", 0) > 5:
                self.logger.error("could not recover after too many errors, closing server.")
                self.close_server.set_result(None)
    

    async def _send_error(self, conn: ServerConnection, e: Exception, id: str | None = None)-> None:
        err = str(e)
        tb = traceback.format_exc()

        obj = {
            "type": "error",
            "error": f"{err}\n{tb}",
        }
        if id is not None:
            obj["uid"] = id
        await self._send(conn, obj)


    async def handle(self, conn: ServerConnection)-> None:

        while True:
            try:
                data = await conn.recv(decode=True)
            except ConnectionClosed:
                # Should we close server on connection end?
                # Would limit to one connection per instance, but would make
                # the app close by itself, which is massive.
                # Would prevent addr already used errs
                self.logger.info("connection closed on recv.")
                return

            self.recv_time = int(time.time() * 1_000)
            self.logger.info("received message: %s", data)
        
            try:
                obj = json.loads(data)
            except Exception as e:
                await self._send_error(conn, e)
                continue

            if not isinstance(obj, dict):
                await self._send_error(conn, TypeError("json value sent from client is not a valid object with the shape {\"key\": value, ...}"))
                continue

            if not "type" in obj:
                await self._send_error(conn, ValueError("missing field \"type\" in message from client"))
                continue

            msg_type = obj.get("type", "unhandled")

            if not isinstance(msg_type, str):
                await self._send_error(conn, TypeError("invalid type for value of field \"type\" in message from client"))
                continue

            msg_handler = self.handlers.get(msg_type, self._on_unhandled)

            try:
                await msg_handler(conn, obj)
            except ConnectionClosed:
                self.logger.info("connection closed on send.")
                return
            except Exception as e:
                await self._send_error(conn, e, obj["uid"] if "uid" in obj else None)
                continue
            continue
        
        return


    async def _on_query(self, conn: ServerConnection, obj: dict)-> None:
        if obj.get("user", "") is None:
            obj["user"] = ""
        message = MsgQuery.model_validate(obj, by_alias=True)

        short_query = []
        long_query = []
        user_query = []

        response = {
            "type": "query",
            "uid": message.uid,
            "from": message.from_,
        }
    
        if "stm" in message.from_:
            idx = message.from_.index("stm") # to get n of stm
            n = message.n[idx]

            short_query = self.dbs.short_term.query(
                coll_name=message.ai_name,
                query_str=message.query + f" ({message.user})",
                n=n,
            )
            response["stm"] = [x.to_dict() for x in short_query]
        
        if "ltm" in message.from_:
            idx = message.from_.index("ltm") # to get n of ltm
            n = message.n[idx]

            long_query = self.dbs.long_term.query(
                coll_name=message.ai_name,
                query_str=f"{message.query} ( {message.user} )",
                n=n,
            )
            response["ltm"] = [x.to_dict() for x in long_query]
        
        if "users" in message.from_:
            idx = message.from_.index("users") # to get n of users
            n = message.n[idx]

            user_query = self.dbs.users.query(
                coll_name=message.ai_name,
                user=message.user,
                n=n,
            )
            response["users"] = [x.to_dict() for x in user_query]
        
        await self._send(conn, response)
        return


    async def _on_store(self, conn: ServerConnection, obj: dict)-> None:
        message = MsgStore.model_validate(obj)
        
        for dest in message.to:
            for mem in message.memories:
                match dest:
                    case "stm":
                        self.dbs.short_term.store(coll_name=message.ai_name, memory=mem)
                    case "ltm":
                        self.dbs.long_term.store(coll_name=message.ai_name, memory=mem)
                    case "users":
                        if mem.user is None: continue # No user associated with mem
                        self.dbs.users.store(coll_name=message.ai_name, user=mem.user, memory=mem)
        
        self.logger.info("stored memories.")
        return


    async def _on_process(self, conn: ServerConnection, obj: dict)-> None:
        message = MsgProcess.model_validate(obj)
        
        res = await self.ai.process(
            ai_name=message.ai_name,
            context=message.context if message.context is not None else [],
            messages=message.messages,
        )

        await self._send(conn, {
            "uid": message.uid,
            "type": "summary",
            "summary": res.summary,
        })

        mem_time = int(time.time() * 1000.0) # timestamp in ms

        score = (res.emotional_intensity + res.importance) / 2.0
        lifetime = floor(score * self.config.long_vdb.max_memory_lifetime)

        self.dbs.short_term.store(message.ai_name, Memory(
            id=str(uuid.uuid4()),
            content=res.summary,
            user=None,
            time=mem_time,
            score=score,
            lifetime=lifetime,
        ))

        for rem in res.remember:
            mem = Memory(
                id=str(uuid.uuid4()),
                content=rem.text,
                user=rem.user,
                time=mem_time,
                score=score,
                lifetime=lifetime,
            )
            self.dbs.short_term.store(message.ai_name, mem)
            if rem.user is not None:
                self.dbs.users.store(coll_name=message.ai_name, user=rem.user, memory=mem)
        
        self.logger.info("processed messages from client.")
        return


    async def _on_evict(self, conn: ServerConnection, obj: dict)-> None:
        message = MsgEvict.model_validate(obj)
        self.dbs.short_term.evict_all(message.ai_name)
        self.logger.info("evicted messages from collection: %s", message.ai_name)
        return
        
    def _on_evict_chunk(self, coll_name: str, mems: list[Memory]) -> None:
        self.logger.info("on_evict_chunk: coll=%s batch=%d", coll_name, len(mems))
        # Try to enqueue quickly; if queue is full, fall back to fire-and-forget off-thread task.
        try:
            self._compress_q.put_nowait((coll_name, mems))
            self.logger.info("on_evict_chunk: queued for async compression (size=%d)", self._compress_q.qsize())
        except asyncio.QueueFull:
            self.logger.warning("compress queue full; running this chunk off-thread immediately")
            asyncio.create_task(asyncio.to_thread(self.compressor.compress_batch, coll_name, mems))
        # return immediately – do NOT block the websocket loop.


    async def _on_clear(self, conn: ServerConnection, obj: dict) -> None:
        msg = MsgClear.model_validate(obj)
        if msg.target == "stm":
            self.dbs.short_term.clear(msg.ai_name)
        elif msg.target == "ltm":
            self.dbs.long_term.clear(msg.ai_name)
        elif msg.target == "users":
            if msg.user:
                self.dbs.users.clear_user(msg.ai_name, msg.user)
            else:
                self.dbs.users.clear_all_users(msg.ai_name)

        await self._send(conn, {
            "type": "ack",
            "uid": msg.uid,
            "op": "clear",
            "target": msg.target,
            "ai_name": msg.ai_name,
            "user": msg.user if hasattr(msg, "user") else None
        })


    async def _on_close(self, conn: ServerConnection, obj: dict)-> None:
        _ = MsgClose.model_validate(obj)
        self.logger.info("received close message.")
        self.close_server.set_result(None)
        return


    async def _on_unhandled(self, conn: ServerConnection, obj: dict)-> None:
        self.logger.info("received unhandled message.")
        raise ValueError("received message with unhandled message type: " + json.dumps(obj))


    async def _compressor_worker(self) -> None:
        self.logger.info("compressor worker: started")
        while True:
            coll_name, mems = await self._compress_q.get()
            try:
                size = self.config.compression.batch_size
                for i in range(0, len(mems), size):
                    sub = mems[i:i+size]
                    await self.compressor.compress_batch_async(coll_name, sub)
            except Exception as e:
                self.logger.exception("compression failed during eviction for '%s': %s", coll_name, e)
            finally:
                self._compress_q.task_done()
