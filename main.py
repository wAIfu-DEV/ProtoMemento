import asyncio
import logging
import sys

import onnxruntime
from websockets.asyncio.server import serve

#from src.messages import generate_schemas
from src.args import        parse_args
from src.dump import        dump_all_dbs
from src.env import         parse_env
from src.config import      parse_config
from src.logging import     logging_init
from src.decay import       periodic_decay
from src.db_bundle import   databases_init
from src.wss_handler import WssHandler


async def main():
    parsed_args = parse_args(sys.argv[1:])
    
    logging_init()
    logger = logging.getLogger("global")

    logger.info("available onnxruntime providers: %s", ", ".join(onnxruntime.get_available_providers()))

    logger.info("reading config & env")
    env = parse_env()
    conf = parse_config()

    #generate_schemas() # generate schemas for inbound Ws messages

    logger.info("initializing databases...")
    bundle = databases_init(conf)

    if parsed_args.dump:
        dump_all_dbs(bundle, conf)
        return

    logger.info("running periodic decay routine")
    decay_task = asyncio.create_task(periodic_decay(bundle.long_term))

    wss_handler = WssHandler(database_bundle=bundle, config=conf, env=env)
    async with serve(wss_handler.handle, host=conf.wss.host, port=conf.wss.port) as wss:
        await wss_handler.bind_and_wait(server=wss)
        # server is being closed
        decay_task.cancel() # may keep program running if not cancelled
    return


if __name__ == "__main__":
    asyncio.run(main())
