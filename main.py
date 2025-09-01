import asyncio
import logging
from websockets.asyncio.server import serve

#from src.messages import generate_schemas
from src.env import parse_env
from src.config import parse_config
from src.vdbs.evicting_vdb import EvictingVdb
from src.vdbs.decaying_vdb import DecayingVdb
from src.vdbs.vdb_chroma import VdbChroma
from src.user_database import UserDatabase
from src.db_bundle import DbBundle
from src.wss_handler import WssHandler


async def periodic_decay(decay_vdb: DecayingVdb):
    while True:
        decay_vdb.decay_all()
        await asyncio.sleep(60 * 60 * 12) # every 6 hours, will skip if date diff < 1


async def main():
    logging.basicConfig(
        format="[%(asctime)s][%(name)s.%(funcName)s] %(message)s",
        datefmt="%m/%d %H:%M:%S",
        level=logging.INFO
    )
    logger = logging.getLogger("global")

    logger.info("reading config & env")
    env = parse_env()
    conf = parse_config()

    #generate_schemas() # Generate schemas for inbound Ws messages

    logger.info("initializing databases...")
    short_size = conf.short_vdb.max_size_before_evict + 10\
                      if conf.short_vdb.max_size_before_evict > 0\
                      else -1

    short_vdb = VdbChroma(db_name="short", size_limit=short_size)
    long_vdb = VdbChroma(db_name="long", size_limit=conf.long_vdb.max_size)

    # implement progressive_eviction from config
    short_evicting = EvictingVdb(
        wrapped_vdb=short_vdb,
        dest_vdb=long_vdb,
        progressive_eviction=conf.short_vdb.progressive_eviction,
        max_size_before_evict=conf.short_vdb.max_size_before_evict,
    )
    long_decaying = DecayingVdb(wrapped_vdb=long_vdb)

    user_db = UserDatabase(size_limit_per_user=conf.user_db.max_size_per_user)

    bundle = DbBundle(short=short_evicting, long=long_decaying, users=user_db)

    # decay routine
    asyncio.create_task(periodic_decay(long_decaying))

    wss_handler = WssHandler(database_bundle=bundle, config=conf, env=env)
    async with serve(wss_handler.handle, host=conf.wss.host, port=conf.wss.port) as wss:
        wss_handler.server = wss
        await asyncio.Future()
    return


if __name__ == "__main__":
    asyncio.run(main())
