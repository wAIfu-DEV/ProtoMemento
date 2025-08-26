from src.memory import Memory, QueriedMemory
from src.vector_database import VectorDataBase

# TODO: implement eviction
class EvictingVdb(VectorDataBase):
    wrapped: VectorDataBase
    dest: VectorDataBase
    max_size: int


    def __init__(self, wrapped_vdb: VectorDataBase, dest_vdb: VectorDataBase, max_size = -1)-> None:
        self.wrapped = wrapped_vdb
        self.dest = dest_vdb
        self.max_size = max_size
        return


    def store(self, coll_name: str, memory: Memory)-> None:
        self.wrapped.store(coll_name, memory)
        return


    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        return self.query(coll_name, query_str, n)
    

    def remove(self, coll_name: str, memory_id: str)-> None:
        self.wrapped.remove(coll_name, memory_id)
        return
    

    def clear(self, coll_name: str)-> None:
        self.wrapped.remove(coll_name)
        return
    
    
    def evict_all()-> None:
        return
        
