import asyncio
from websockets.asyncio.server import serve

from src.env import parse_env
from src.config import parse_config
from src.evicting_vdb import EvictingVdb
from src.db_bundle import DbBundle
from src.vdb_chroma import VdbChroma
from src.user_database import UserDatabase
from src.wss_handler import WssHandler


async def main():
    env = parse_env()
    conf = parse_config()

    short_vdb = VdbChroma(
        db_name="short",
        size_limit=conf.short_vdb.max_size_before_evict + 10\
                   if conf.short_vdb.max_size_before_evict > 0\
                   else -1
    )
    long_vdb = VdbChroma(
        db_name="long",
        size_limit=conf.long_vdb.max_size
    )

    # TODO: configure max_size param
    short_evicting = EvictingVdb(
        wrapped_vdb=short_vdb,
        dest_vdb=long_vdb,
        max_size_before_evict=conf.short_vdb.max_size_before_evict,
    )
    user_db = UserDatabase(
        size_limit_per_user=conf.user_db.max_size_per_user
    )

    bundle = DbBundle(short=short_evicting, long=long_vdb, users=user_db)
    wss_handler = WssHandler(database_bundle=bundle, config=conf, env=env)

    # TODO: parameterize port & host
    async with serve(wss_handler.handle, host="127.0.0.1", port=4286) as wss:
        wss_handler.server = wss
        await asyncio.Future()
    return


if __name__ == "__main__":
    asyncio.run(main())
