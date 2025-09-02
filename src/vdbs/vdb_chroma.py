import logging
import os
from chromadb import Client, ClientAPI, Collection, Settings
from chromadb.errors import NotFoundError

from src.vdbs.vector_database import VectorDataBase
from src.memory import Memory, QueriedMemory

class VdbChroma(VectorDataBase):
    client: ClientAPI = None
    coll_cache: dict[str, Collection]
    size_limit: int = -1
    name: str
    logger: logging.Logger


    def __init__(self, db_name: str, size_limit: int = -1)-> None:
        self.logger = logging.getLogger(f"{self.__class__.__name__}({db_name})")
        self.size_limit = size_limit
        self.name = db_name

        path = os.path.join(".", "vectors", db_name)
        os.makedirs(path, exist_ok=True)

        settings = Settings()
        settings.is_persistent = True
        settings.anonymized_telemetry = False
        settings.persist_directory = path

        self.client = Client(settings=settings)
        self.coll_cache = {}  # instance-local cache
        self.logger.info("initialized %s vector database", db_name)
        return


    def _unique_coll_name(self, coll_name: str)-> str:
        return coll_name + f"_{self.name}"


    def _get_collection(self, coll_name: str)-> Collection:
        unique_name = self._unique_coll_name(coll_name)

        collection: Collection
        if not unique_name in self.coll_cache:
            collection = self.client.get_or_create_collection(name=unique_name)
            self.coll_cache[unique_name] = collection
        else:
            collection = self.coll_cache[unique_name]
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
        metadata = {"t": memory.time}

        if memory.user:                    # only add when non-empty truthy
            metadata["u"] = memory.user
        if memory.score is not None:
            metadata["s"] = memory.score
        if memory.lifetime is not None:
            metadata["l"] = memory.lifetime

        self._get_collection(coll_name).add(
            ids=[memory.id],
            documents=[memory.content],
            metadatas=[metadata],
        )

        if self.size_limit >= 0:
            self._restrict_size(coll_name)


    def remove(self, coll_name: str, memory_id: str)-> None:
        self._get_collection(coll_name).delete(ids=[memory_id])
        return


    def query(self, coll_name: str, query_str: str, n: int)-> list[QueriedMemory]:
        final: list[QueriedMemory] = []

        res = self._get_collection(coll_name).query(
            query_texts=[query_str],
            n_results=n,
        )

        res_len = len(res["documents"][0])
        for i in range(res_len):
            meta = res["metadatas"][0][i]
            mem: Memory = Memory(
                id=      res["ids"][0][i],
                content= res["documents"][0][i],
                time=    meta.get("t", 0),
                user=    meta.get("u", None),
                score=   meta.get("s", None),
                lifetime=meta.get("l", None),
            )
            qmem: QueriedMemory = QueriedMemory(
                memory=mem,
                distance=res["distances"][0][i],
            )
            final.append(qmem)

        return final


    def pop_oldest(self, coll_name: str, n: int = 1) -> list[Memory]:
        coll = self._get_collection(coll_name)
        res = coll.get(ids=None, offset=0, limit=n)

        final: list[Memory] = []
        res_len = len(res["documents"])
        for i in range(res_len):
            meta = res["metadatas"][i]
            mem: Memory = Memory(
                id=      res["ids"][i],
                content= res["documents"][i],
                time=    meta.get("t", 0),
                user=    meta.get("u", None),
                score=   meta.get("s", None),
                lifetime=meta.get("l", None),
            )
            final.append(mem)
            coll.delete(ids=[mem.id])
        
        return final


    def clear(self, coll_name: str)-> None:
        unique_name = self._unique_coll_name(coll_name)
        try:
            self.client.delete_collection(unique_name)
        except NotFoundError:
            pass
        self.coll_cache[unique_name] = self.client.get_or_create_collection(name=unique_name)
        return


    def count(self, coll_name: str)-> int:
        c = self._get_collection(coll_name).count()
        self.logger.info("count: coll=%s_%s -> %d", coll_name, self.name, c)
        return c



    def get_collection_names(self) -> list[str]:
        suffix = f"_{self.name}"
        all_cols = self.client.list_collections()
        suffix_cols = [c.name for c in all_cols if c.name.endswith(suffix)]
        logical_names = [name[:-len(suffix)] for name in suffix_cols]
        return logical_names

