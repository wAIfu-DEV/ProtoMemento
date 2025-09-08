import logging
from src.memory import Memory, QueriedMemory
from src.vdbs.vector_database import VectorDataBase
from typing import Callable, List, Optional


class EvictingVdb(VectorDataBase):
    wrapped: VectorDataBase
    dest: VectorDataBase
    prog_evict: bool
    max_size: int
    evict_fraction: float
    evict_min_batch: int
    logger: logging.Logger
    on_evict: Optional[Callable[[str, list[Memory]], None]]


    def __init__(
        self,
        wrapped_vdb: VectorDataBase,
        dest_vdb: VectorDataBase,
        progressive_eviction: bool = True,
        max_size_before_evict: int = -1,
        evict_fraction: float = 0.0,
        evict_min_batch: int = 1
    )-> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.wrapped = wrapped_vdb
        self.dest = dest_vdb
        self.prog_evict = progressive_eviction
        self.max_size = max_size_before_evict
        # clamp + store
        self.evict_fraction = 0.0 if evict_fraction < 0.0 else (1.0 if evict_fraction > 1.0 else float(evict_fraction))
        self.evict_min_batch = max(0, int(evict_min_batch))
        self.on_evict = None
        return
        

    def set_on_evict(self, cb: Callable[[str, list[Memory]], None]) -> None:
        self.on_evict = cb
        self.logger.info("set_on_evict: handler installed = %s", bool(self.on_evict))


    def _emit_evict(self, coll_name: str, evicted: List[Memory]) -> None:
        self.logger.info("emit_evict: coll=%s batch=%d handler=%s", coll_name, len(evicted), bool(self.on_evict))
        if not evicted:
            return
        if self.on_evict is not None:
            self.on_evict(coll_name, evicted)
        else:
            # fallback: raw copy to LTM if no handler is set
            for m in evicted:
                self.dest.store(coll_name, m)


    def _evict_oldest(self, coll_name: str)-> bool:
        mems = self.wrapped.pop_oldest(coll_name, n=1)
        if len(mems) > 0:
            self.dest.store(coll_name, mems[0])
        return len(mems) > 0


    def _evict_overflow(self, coll_name: str) -> None:
        if self.prog_evict and self.max_size > 0:
            current = self.wrapped.count(coll_name)
            self.logger.info("evict_overflow: coll=%s count=%d max=%d", coll_name, current, self.max_size)
            if current <= self.max_size:
                return

            overflow = current - self.max_size

            # decide how many to evict:
            # - fraction mode: evict at least floor(current * fraction)
            # - overflow-only if fraction == 0
            # - always respect min batch, never exceed current
            if self.evict_fraction > 0.0:
                frac_amt = int(current * self.evict_fraction)
                n_to_evict = max(overflow, frac_amt, self.evict_min_batch)
            else:
                n_to_evict = max(overflow, self.evict_min_batch)

            n_to_evict = min(n_to_evict, current)

            self.logger.info(
                "evict_overflow: decided n=%d (overflow=%d, fraction=%.2f, min=%d)",
                n_to_evict, overflow, self.evict_fraction, self.evict_min_batch
            )

            evicted: List[Memory] = []
            remain = n_to_evict
            while remain > 0:
                chunk_n = min(256, remain)
                popped = self.wrapped.pop_oldest(coll_name, n=chunk_n)
                self.logger.info("evict_overflow: popped=%d", len(popped))
                if not popped:
                    break
                evicted.extend(popped)
                remain -= len(popped)

            self._emit_evict(coll_name, evicted)
        return


    def store(self, coll_name: str, memory: Memory)-> None:
        self.wrapped.store(coll_name, memory)
        post = self.wrapped.count(coll_name)
        self.logger.info("store: coll=%s post_count=%d", coll_name, post)
        self._evict_overflow(coll_name)
        return


    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        return self.wrapped.query(coll_name, query_str, n)


    def remove(self, coll_name: str, memory_id: str)-> None:
        self.wrapped.remove(coll_name, memory_id)
        return


    def clear(self, coll_name: str)-> None:
        self.wrapped.clear(coll_name)
        return


    def count(self, coll_name: str)-> int:
        return self.wrapped.count(coll_name)
    

    def pop_oldest(self, coll_name: str, n: int | None = 1)-> list[Memory]:
        return self.wrapped.pop_oldest(coll_name, n)
    

    def peek_oldest(self, coll_name: str, n: int | None = 1) -> list[Memory]:
        return self.wrapped.peek_oldest(coll_name, n)


    def evict_all(self, coll_name: str) -> None:
        total_evicted = 0
        while True:
            chunk = self.wrapped.pop_oldest(coll_name, n=256)
            self.logger.info("evict_all: popped=%d", len(chunk))
            if not chunk:
                break
            total_evicted += len(chunk)
            self._emit_evict(coll_name, chunk)
        self.logger.info("evict_all: coll=%s total=%d", coll_name, total_evicted)
        return


    def get_collection_names(self) -> list[str]:
        return self.wrapped.get_collection_names()
