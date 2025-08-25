import json
from typing import Callable, Self
from src.databases import MemoryDatabases
from websockets.asyncio.server import Server, ServerConnection
from websockets import ConnectionClosed

class WssHandler:
    dbs: MemoryDatabases
    server: Server = None

    handlers: dict[str, Callable[[Self, dict], None]] = {}


    def __init__(self, database_bundle: MemoryDatabases)-> None:
        self.dbs = database_bundle
        self.handlers = {
            "query": self._on_query,
            "store": self._on_store,
            "process": self._on_process,
            "unhandled": self._on_unhandled,
        }
        return


    async def handle(self, conn: ServerConnection)-> None:

        while True:
            try:
                data = await conn.recv()
            except ConnectionClosed:
                # Should we close server on connection end?
                # Would limit to one connection per instance, but would make
                # the app close by itself, which is massive.
                # Would prevent addr already used errs
                return
        
            try:
                obj: dict = json.loads(data)
            except Exception as e:
                # TODO: send to err pipe
                raise e

            if not "type" in obj:
                # TODO: send to err pipe
                raise TypeError()

            msg_type = obj.get("type", "unhandled")

            if not isinstance(msg_type, str):
                # TODO: send to err pipe
                raise TypeError()

            msg_handler = self.handlers.get(msg_type, self._on_unhandled)
            msg_handler(self, obj)
            return


    async def _on_query(self, obj: dict)-> None:
        return


    async def _on_store(self, obj: dict)-> None:
        return
    
    
    async def _on_process(self, obj: dict)-> None:
        return
    

    async def _on_unhandled(self, obj: dict)-> None:
        return
