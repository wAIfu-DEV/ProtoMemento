import asyncio
from src.vdbs.decaying_vdb import DecayingVdb


async def periodic_decay(decay_vdb: DecayingVdb):
    try:
        while True:
            decay_vdb.decay_all()
            await asyncio.sleep(60 * 60 * 12) # every 6 hours, will skip if date diff < 1
    except asyncio.CancelledError:
        return
