# pip install websockets

import asyncio
import os
import socket
import subprocess
import json
import uuid

from typing import Callable, Literal
from enum import Enum

from websockets.asyncio.client import ClientConnection, connect

from typing import Optional, Self
from pydantic import BaseModel, Field


class Memory(BaseModel):
    id: str = Field(...)
    content: str = Field(...)
    time: int = Field(...)

    user: Optional[str] = Field(default=None)
    score: Optional[float] = Field(default=None)
    lifetime: Optional[int] = Field(default=None)

    class Config:
        populate_by_name = True
    

    @staticmethod
    def from_dict(input: dict)-> Self:
        return Memory(
            id=input.get("id", uuid.uuid4()),
            content=input.get("content", ""),
            time=input.get("time", 0),
            user=input.get("user", None),
            score=input.get("score", None),
            lifetime=input.get("lifetime", None),
        )

    def to_dict(self)-> dict:
        obj = {
            "id": str(self.id),
            "content": str(self.content),
            "time": int(self.time),
        }

        if self.user is not None:
            obj["user"] = str(self.user)
        if self.score is not None:
            obj["score"] = float(self.score)
        if self.lifetime is not None:
            obj["lifetime"] = int(self.lifetime)
        return obj

    def to_json(self)-> str:
        return json.dumps(self.to_dict())


class QueriedMemory(BaseModel):
    memory: Memory = Field(...)
    distance: float = Field(...)
    
    @staticmethod
    def from_dict(input: dict)-> Self:
        mem: dict | None = input.get("memory", None),
        return QueriedMemory(
            memory=Memory(
                id=mem.get("id", uuid.uuid4()),
                content=mem.get("content", ""),
                time=mem.get("time", 0),
                user=mem.get("user", None),
                score=mem.get("score", None),
                lifetime=mem.get("lifetime", None),
            ),
            distance=input.get("distance")
        )

    def to_dict(self)-> dict:
        return {
            "memory": self.memory.to_dict(),
            "distance": float(self.distance),
        }
    
    def to_json(self)-> str:
        return json.dumps(self.to_dict())


class OpenLlmMsg(BaseModel):
    role: Literal["assistant", "user", "system"] | str = Field(...)
    content: str = Field(...)
    name: Optional[str] = Field(default=None)

    class Config:
        populate_by_name = True


class DbEnum(Enum):
    SHORT_TERM = "stm"
    LONG_TERM = "ltm"
    USERS = "users"


class QueryResult:
    short_term: list[QueriedMemory]
    long_term: list[QueriedMemory]
    users: list[Memory]


class CountResult:
    short_term: int
    long_term: int


class Memento:
    _conn: ClientConnection
    _proc: subprocess.Popen
    _uri: str

    _summary_cb: Callable[[str], None] = None
    _pending_requests: dict[str, asyncio.Future] = {}


    def __init__(self, abs_dir: str = "", host: str = "127.0.0.1", port: int = 4286, loop=None):
        self._conn = None
        self._uri = f"wss://{host}:{str(port)}"

        self._proc = None
        if not self._is_port_open(host, port, timeout=2.0):
            if abs_dir == "":
                raise Exception("Memento instance is not open, and no abs_path have been provided to start a new one.")

            py_path = os.path.join(abs_dir, "venv", "Scripts", "python.exe")
            main_path = os.path.join(abs_dir, "main.py")

            if not os.path.isfile(py_path) or not os.path.isfile(main_path):
                raise Exception("abs_dir provided does not point to a valid Memento directory.")

            self._proc = subprocess.Popen([py_path, main_path], cwd=abs_dir)

            if not self._is_port_open(host, port, timeout=10.0):
                raise Exception("failed to run new Memento instance.")

        self._loop = loop or asyncio.get_event_loop()
        self._ws_task = self.loop.create_task(self._runner())
    

    def __del__(self):
        if self._proc != None:
            self._proc.kill()
        
        if self._conn != None:
            self._conn.close()
    

    def _is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False
    
    
    async def _runner(self):
        async with connect(uri=self._uri) as ws:
            self._conn = ws
            async for message in ws:
                try:
                    obj = json.loads(message)
                except Exception as e:
                    raise Exception("received malformed json from Memento.", e)
                
                if "type" not in obj:
                    raise Exception("received malformed payload from Memento. missing field: \"type\"")

                if not isinstance(obj["type"], str):
                    raise Exception("received malformed payload from Memento. field: \"type\" is not of type str")

                if "uid" not in obj:
                    raise Exception("received malformed payload from Memento. missing field: \"uid\"")
                
                if not isinstance(obj["uid"], str):
                    raise Exception("received malformed payload from Memento. field: \"uid\" is not of type str")

                message_type = obj["type"]
                message_id = obj["uid"]

                match message_type:
                    case "query":
                        res = QueryResult()
                        dbs: list[str] = obj["from"]
                        
                        if "stm" in dbs:
                            res.short_term = [QueriedMemory.from_dict(x) for x in obj["stm"]]
                        if "ltm" in dbs:
                            res.long_term = [QueriedMemory.from_dict(x) for x in obj["ltm"]]
                        if "users" in dbs:
                            res.users = [Memory.from_dict(x) for x in obj["users"]]

                        if message_id in self._pending_requests:
                            future = self._pending_requests.pop(message_id, None)
                            if future:
                                future.set_result(res)
                        else:
                            raise Exception("received unhandled response to query request.")

                    case "summary":
                        if self._summary_cb is None:
                            continue
                        
                        summary: str = obj["summary"]
                        self._summary_cb(summary)
                    
                    case "count":
                        res = CountResult()
                        
                        if "stm" in obj:
                            res.short_term = obj["stm"]
                        if "ltm" in obj:
                            res.long_term = obj["ltm"]
                        
                        if message_id in self._pending_requests:
                            future = self._pending_requests.pop(message_id, None)
                            if future:
                                future.set_result(res)
                        else:
                            raise Exception("received unhandled response to count request.")
                        
    
    
    def set_on_summary(self, cb: Callable[[str], None]):
        self._summary_cb = cb
    

    async def query(self,
            query_str: str,
            collection_name: str = "default",
            user: str | None = None,
            _from: list[DbEnum] = [DbEnum.SHORT_TERM, DbEnum.LONG_TERM, DbEnum.USERS],
            n: list[int] = [1, 1, 1],
            timeout: float = 5.0,
        )-> QueryResult:

        req_id = str(uuid.uuid4())
        future: asyncio.Future[QueryResult] = asyncio.Future()
        self._pending_requests[req_id] = future
        
        await self._conn.send(
            message=json.dumps({
                "uid": req_id,
                "type": "query",
                "query": query_str,
                "ai_name": collection_name,
                "user": user,
                "from": [x.value for x in _from],
                "n": n,
            }),
            text=True,
        )

        try:
            async with asyncio.timeout(timeout):
                return await future
        except asyncio.TimeoutError as e:
            future.set_result(None)
            raise e


    async def store(self,
            memories: list[Memory],
            collection_name: str = "default",
            to: list[DbEnum] = [DbEnum.SHORT_TERM, DbEnum.USERS],
        )-> None:

        await self._conn.send(
            message=json.dumps({
                "uid": str(uuid.uuid4()),
                "type": "store",
                "memories": [x.to_dict() for x in memories],
                "ai_name": collection_name,
                "to": [x.value for x in to],
            }),
            text=True,
        )


    async def process(self,
            messages: list[OpenLlmMsg],
            context: list[OpenLlmMsg] = None,
            collection_name: str = "default",
        )-> None:

        if context is None:
            context = []

        await self._conn.send(
            message=json.dumps({
                "uid": str(uuid.uuid4()),
                "type": "process",
                "ai_name": collection_name,
                "messages": [x.model_dump(mode="json") for x in messages],
                "context": [x.model_dump(mode="json") for x in context],
            }),
            text=True,
        )


    async def close(self)-> None:
        await self._conn.send(
            message=json.dumps({
                "uid": str(uuid.uuid4()),
                "type": "close",
            }),
            text=True,
        )
    
    async def evict(self, collection_name: str = "default")-> None:
        await self._conn.send(
            message=json.dumps({
                "uid": str(uuid.uuid4()),
                "type": "evict",
                "ai_name": collection_name,
            }),
            text=True,
        )
    
    async def clear(self,
            collection_name: str = "default",
            target: list[DbEnum] = [DbEnum.SHORT_TERM, DbEnum.LONG_TERM, DbEnum.USERS],
        )-> None:

        await self._conn.send(
            message=json.dumps({
                "uid": str(uuid.uuid4()),
                "type": "clear",
                "ai_name": collection_name,
                "target": [x.value for x in target],
            }),
            text=True,
        )
    
    async def count(self,
            collection_name: str = "default",
            _from: list[DbEnum] = [DbEnum.SHORT_TERM, DbEnum.LONG_TERM, DbEnum.USERS],
            timeout: float = 5.0,
        )-> None:

        req_id = str(uuid.uuid4())
        future: asyncio.Future[CountResult] = asyncio.Future()
        self._pending_requests[req_id] = future
        
        await self._conn.send(
            message=json.dumps({
                "uid": req_id,
                "type": "count",
                "ai_name": collection_name,
                "from": [x.value for x in _from],
            }),
            text=True,
        )

        try:
            async with asyncio.timeout(timeout):
                return await future
        except asyncio.TimeoutError as e:
            future.set_result(None)
            raise e
