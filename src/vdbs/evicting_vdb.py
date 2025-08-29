import logging
from src.memory import Memory, QueriedMemory
from src.vdbs.vector_database import VectorDataBase

class EvictingVdb(VectorDataBase):
    wrapped: VectorDataBase
    dest: VectorDataBase
    max_size: int
    logger: logging.Logger


    def __init__(self, wrapped_vdb: VectorDataBase, dest_vdb: VectorDataBase, max_size_before_evict = -1)-> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.wrapped = wrapped_vdb
        self.dest = dest_vdb
        self.max_size = max_size_before_evict
        return


    def _evict_oldest(self, coll_name: str)-> None:
        mem = self.wrapped.pop_oldest(coll_name)
        self.dest.store(coll_name, mem)


    def _evict_overflow(self, coll_name: str)-> None:
        if self.max_size < 0:
            return
        
        while self.wrapped.count(coll_name) > self.max_size:
            self._evict_oldest(coll_name)
        return


    def store(self, coll_name: str, memory: Memory)-> None:
        self.wrapped.store(coll_name, memory)
        self._evict_overflow(coll_name)
        return


    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        return self.wrapped.query(coll_name, query_str, n)


    def remove(self, coll_name: str, memory_id: str)-> None:
        self.wrapped.remove(coll_name, memory_id)
        return


    def clear(self, coll_name: str)-> None:
        self.wrapped.remove(coll_name)
        return


    def count(self, coll_name: str)-> int:
        return self.wrapped.count(coll_name)
    

    def pop_oldest(self, coll_name: str)-> Memory:
        return self.wrapped.pop_oldest(coll_name)


    def evict_all(self, coll_name: str)-> None:
        while self.wrapped.count(coll_name) > 0:
            self._evict_oldest(coll_name)
        return
        
