import asyncio
from websockets.asyncio.server import serve

from src.evicting_vdb import EvictingVdb
from src.databases import MemoryDatabases
from src.vdb_chroma import VdbChroma
from src.user_database import UserDatabase
from src.wss_handler import WssHandler


async def main():
    short_vdb = VdbChroma(db_name="short", size_limit=500)
    long_vdb = VdbChroma(db_name="long", size_limit=5_000)
    user_db = UserDatabase(size_limit_per_user=100)

    # TODO: configure max_size param
    short_evicting = EvictingVdb(
        wrapped_vdb=short_vdb,
        dest_vdb=long_vdb,
        max_size=-1,
    )

    bundle = MemoryDatabases(short=short_evicting, long=long_vdb, users=user_db)
    wss_handler = WssHandler(database_bundle=bundle)

    # TODO: parameterize port & host
    async with serve(wss_handler.handle, host="127.0.0.1", port=4286) as wss:
        wss_handler.server = wss
        await asyncio.Future()
    return


if __name__ == "__main__":
    asyncio.run(main())
