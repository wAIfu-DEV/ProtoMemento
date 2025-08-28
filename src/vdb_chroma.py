import os
from chromadb import Client, ClientAPI, Collection, Settings
from src.vector_database import VectorDataBase
from src.memory import Memory, QueriedMemory

class VdbChroma(VectorDataBase):
    client: ClientAPI = None
    coll_cache: dict[str, Collection] = {}
    size_limit: int = -1


    def __init__(self, db_name: str, size_limit: int = -1)-> None:
        self.size_limit = size_limit
        settings = Settings()
        settings.is_persistent = True
        path = os.path.join(".", "vectors", db_name)
        os.makedirs(path, exist_ok=True)
        settings.persist_directory = path
        self.client = Client(settings=settings)
        super().__init__()
        return


    def _get_collection(self, coll_name: str)-> Collection:
        collection: Collection
        if not coll_name in self.coll_cache:
            collection = self.client.get_or_create_collection(name=coll_name)
            self.coll_cache[coll_name] = collection
        else:
            collection = self.coll_cache[coll_name]
        return collection


    def _restrict_size(self, coll_name: str)-> None:
        if self.size_limit < 0:
            return

        collection = self._get_collection(coll_name)
        collection_size = collection.count()
        if collection_size <= self.size_limit:
            return
        
        size_diff = collection_size - self.size_limit
        items = collection.get(ids=None, limit=size_diff)
        ids_to_remove = items['ids']
        collection.delete(ids=ids_to_remove)
        return


    def store(self, coll_name: str, memory: Memory)-> None:
        self._get_collection(coll_name).add(
            documents=[memory.content],
            metadatas=[{"timestamp": memory.time, "score": 0.0, "user": memory.user}], # TODO implement score and decay sys
            ids=[memory.id]
        )

        if self.size_limit >= 0:
            self._restrict_size()
        return


    def remove(self, coll_name: str, memory_id: str)-> None:
        self._get_collection(coll_name).delete(ids=[memory_id])
        return


    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        final: list[QueriedMemory] = []

        query_res = self._get_collection(coll_name).query(
            query_texts=[query_str],
            n_results=n,
        )

        results_len = len(query_res["documents"][0])
        for i in range(results_len):
            mem: Memory = Memory(
                id=query_res["ids"][0][i],
                content=query_res["documents"][0][i],
                time=query_res["metadatas"][0][i]["timestamp"],
                user=query_res["metadatas"][0][i]["user"],
            )
            qmem: QueriedMemory = QueriedMemory(
                memory=mem,
                distance=query_res["distances"][0][i],
            )
            final.append(qmem)

        return final


    def pop_oldest(self, coll_name: str)-> Memory:
        coll = self._get_collection(coll_name)
        res = coll.get(ids=None, offset=0, limit=1)
        mem: Memory = Memory(
            id=res["ids"][0],
            content=res["documents"][0],
            time=res["metadatas"][0]["timestamp"],
            user=res["metadatas"][0]["user"],
        )
        coll.delete(ids=[mem.id])
        return mem


    def clear(self, coll_name: str)-> None:
        self.client.delete_collection(coll_name)
        self.coll_cache[coll_name] = self.client.create_collection(coll_name)
        return
    

    def count(self, coll_name: str)-> int:
        return self._get_collection(coll_name).count()
