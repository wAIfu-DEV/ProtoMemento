import asyncio
from websockets.asyncio.server import serve, Server

from src.databases import MemoryDatabases
from src.vdb_chroma import VdbChroma
from src.user_database import UserDatabase
from src.ws_handler import WssHandler


async def main():
    database_bundle = MemoryDatabases(
        # TODO: add eviction system for short mem
        short=VdbChroma(db_name="short", size_limit=500),
        long=VdbChroma(db_name="long", size_limit=5_000),
        users=UserDatabase(size_limit_per_user=100),
    )

    wss_handler = WssHandler(database_bundle)

    # TODO: parameterize port & host
    async with serve(wss_handler.handle, host="127.0.0.1", port=4286) as wss:
        wss_handler.server = wss
        await asyncio.Future()
    return


if __name__ == "__main__":
    asyncio.run(main())
