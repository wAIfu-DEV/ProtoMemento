import json
import time
import traceback
import uuid
from typing import Callable, Coroutine, Literal
from pathlib import Path

from websockets.asyncio.server import Server, ServerConnection
from websockets import ConnectionClosed

from src.config import Config
from src.memory import Memory
from src.ai import AI
from src.messages import MessageTypes, MsgEvict, MsgQuery, MsgStore, MsgProcess
from src.db_bundle import DbBundle





class WssHandler:
    config: Config
    env: dict

    dbs: DbBundle
    server: Server = None
    ai: AI

    handlers: dict[MessageTypes, Callable[[ServerConnection, dict], Coroutine]] = {}


    def __init__(self, database_bundle: DbBundle, config: Config, env: dict)-> None:
        self.config = config
        self.env = env
        
        self.dbs = database_bundle
        self.handlers = {
            "query": self._on_query,
            "store": self._on_store,
            "process": self._on_process,
            "evict": self._on_evict,

            "unhandled": self._on_unhandled,
        }

        self.ai = AI(
            base_url=config.openllm.base_url,
            model_name=config.openllm.model,
            api_key=env["OPENAI_API_KEY"],
            config=config
        )
        return


    async def _send_error(self, conn: ServerConnection, e: Exception, id: str | None = None)-> None:
        obj = {
            "type": "error",
            "error": str(e) + "\n" + traceback.format_exc(),
        }
        if not id is None:
            obj["uid"] = id
        await conn.send(json.dumps(obj), text=True)


    async def handle(self, conn: ServerConnection)-> None:

        while True:
            try:
                data = await conn.recv(decode=True)
            except ConnectionClosed:
                # Should we close server on connection end?
                # Would limit to one connection per instance, but would make
                # the app close by itself, which is massive.
                # Would prevent addr already used errs
                return
        
            try:
                obj: dict = json.loads(data)
            except Exception as e:
                self._send_error(conn, e)
                continue

            if not "type" in obj:
                self._send_error(conn, TypeError('missing field "type" in message from client'))
                continue

            msg_type = obj.get("type", "unhandled")

            if not isinstance(msg_type, str):
                self._send_error(conn, TypeError('invalid type for value of field "type" in message from client'))
                continue

            msg_handler = self.handlers.get(msg_type, self._on_unhandled)

            try:
                await msg_handler(conn, obj)
            except ConnectionClosed:
                return
            except Exception as e:
                self._send_error(conn, e, obj["uid"] if "uid" in obj else None)
                continue
            continue
        
        return


    async def _on_query(self, conn: ServerConnection, obj: dict)-> None:
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
        
        resp_str = json.dumps(response)
        await conn.send(resp_str, text=True)
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

        return


    async def _on_process(self, conn: ServerConnection, obj: dict)-> None:
        message = MsgProcess.model_validate(obj)
        
        res = await self.ai.process(
            ai_name=message.ai_name,
            context=message.context if not message.context is None else [],
            messages=message.messages,
        )
        score = (res.emotional_intensity + res.importance) / 2.0
        mem_time = int(time.time() * 1000.0)

        # TODO: implement score system
        self.dbs.short_term.store(message.ai_name, Memory(
            id=uuid.uuid4(),
            content=res.summary,
            user=None,
            time=mem_time,
        ))

        for rem in res.remember:
            mem = Memory(
                id=uuid.uuid4(),
                content=rem.text,
                user=rem.user,
                time=mem_time,
            )
            self.dbs.short_term.store(message.ai_name, mem)
            if not rem.user is None:
                self.dbs.users.store(message.ai_name, rem.user, mem)
         
        return


    async def _on_evict(self, conn: ServerConnection, obj: dict)-> None:
        message = MsgEvict.model_validate(obj)
        self.dbs.short_term.evict_all(message.ai_name)
        return


    async def _on_unhandled(self, conn: ServerConnection, obj: dict)-> None:
        raise TypeError("Received message with unhandled message type: " + json.dumps(obj))
