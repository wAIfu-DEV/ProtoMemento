import asyncio
import logging
import traceback
from typing import Callable, Coroutine


def with_retry(fn: Callable, *args, max_retries: int = 5, **kwargs):
    logger = logging.getLogger("with_retry")
    tries = 1

    while tries <= max_retries:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning("retried on coroutine exception:\n%s", traceback.format_exc())
            tries += 1


async def with_retry_async(cr: Callable[[], Coroutine], *args, max_retries: int = 5, **kwargs):
    logger = logging.getLogger("with_retry_async")
    tries = 1

    while tries <= max_retries:
        try:
            return await cr(*args, **kwargs)
        except Exception as e:
            logger.warning("retried on coroutine exception:\n%s", traceback.format_exc())
            tries += 1


async def with_retry_and_timeout_async(cr: Callable[[], Coroutine], *args, max_retries: int = 5, timeout_each: float = 5.0, **kwargs):
    logger = logging.getLogger("with_retry_and_timeout_async")
    tries = 1

    while tries <= max_retries:
        try:
            async with asyncio.timeout(timeout_each):
                return await cr(*args, **kwargs)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            logger.warning("retried on coroutine timeout:\n%s", traceback.format_exc())
        except Exception as e:
            logger.warning("retried on coroutine exception:\n%s", traceback.format_exc())
        finally:
            tries += 1
