import logging
from src.memory import Memory, QueriedMemory
from src.vdbs.vector_database import VectorDataBase

# TODO: implement decay
class DecayingVdb(VectorDataBase):
    wrapped: VectorDataBase
    logger: logging.Logger


    def __init__(self, wrapped_vdb: VectorDataBase)-> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.wrapped = wrapped_vdb
        return


    def store(self, coll_name: str, memory: Memory)-> None:
        self.wrapped.store(coll_name, memory)
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


    def decay_all(self, coll_name: str)-> None:
        self.logger.info("starting decay routine...")
        # TODO: implement decay using "l" metadata field representing lifetime
        self.logger.info("finished decaying all memories")
        return
        
