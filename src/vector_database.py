from src.memory import Memory, QueriedMemory

class VectorDataBase:
    def __init__(self)-> None:
        return

    def store(self, coll_name: str, memory: Memory)-> None:
        return

    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        return []
    
    def remove(self, coll_name: str, memory_id: str)-> None:
        return
    
    def clear(self, coll_name: str)-> None:
        return
    
    def count(self, coll_name: str)-> int:
        return 0
        
