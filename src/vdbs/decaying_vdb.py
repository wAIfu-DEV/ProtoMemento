import datetime
import json
import logging
import os
from src.memory import Memory, QueriedMemory
from src.vdbs.vector_database import VectorDataBase

# TODO: implement decay
class DecayingVdb(VectorDataBase):
    wrapped: VectorDataBase
    logger: logging.Logger

    _DECAY_META_DIR = os.path.join(".", "decay_meta")
    _CHUNK_SIZE = 500

    def __init__(self, wrapped_vdb: VectorDataBase)-> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.wrapped = wrapped_vdb
        os.makedirs(self._DECAY_META_DIR, exist_ok=True)
        return
    

    def _meta_path(self, coll_name: str) -> str:
        safe_name = coll_name.replace("/", "_")
        return os.path.join(self._DECAY_META_DIR, f"{safe_name}_decay.json")


    def _load_last_run(self, coll_name: str) -> datetime.datetime:
        path = self._meta_path(coll_name)
        if not os.path.isfile(path):
            return datetime.datetime.now(tz=datetime.timezone.utc)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            ts = data.get("last_run")
            if isinstance(ts, (int, float)):
                return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        
        return datetime.datetime.now(tz=datetime.timezone.utc)


    def _save_last_run(self, coll_name: str, when: datetime.datetime) -> None:
        path = self._meta_path(coll_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_run": when.timestamp()}, f)


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


    def pop_oldest(self, coll_name: str, n: int = 1)-> list[Memory]:
        return self.wrapped.pop_oldest(coll_name, n)


    def decay_all(self, coll_name: str)-> None:
        self.logger.info("running decay for collection '%s'...", coll_name)

        last_run = self._load_last_run(coll_name)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        elapsed_seconds = (now - last_run).total_seconds()
        elapsed_days = int(elapsed_seconds // (24 * 60 * 60))

        if elapsed_days <= 0:
            self.logger.debug("decay skipped – only %.2f seconds since last run.", elapsed_seconds)
            return

        self.logger.info("decay interval: %d day(s) since %s.", elapsed_days, last_run.isoformat())

        total = self.wrapped.count(coll_name)
        if total == 0:
            self.logger.debug("collection empty – nothing to decay.")
            self._save_last_run(coll_name, now)
            return

        processed = 0
        while processed < total:
            # removes _CHUNK_SIZE memories from the front of vdb
            chunk = self.wrapped.pop_oldest(
                coll_name,
                n=max(min(self._CHUNK_SIZE, total - processed), 0)
            )

            if len(chunk) == 0:
                break

            for mem in chunk:
                if mem.lifetime is None:
                    self.logger.debug("expiring memory %s (lifetime is None).", mem.id)
                    continue
            
                # TODO: evaluate usefulness, acts as protection of core memories
                if (not mem.score is None) and mem.score > 0.85:
                    self.wrapped.store(coll_name, mem)
                    continue

                new_life = mem.lifetime - elapsed_days
                if new_life <= 0:
                    # memory death
                    self.logger.debug("expiring memory %s (lifetime %d → %d).", mem.id, mem.lifetime, new_life)
                    continue

                # update memory
                mem.lifetime = new_life
                self.wrapped.store(coll_name, mem)

            processed += len(chunk)
            self.logger.debug("processed %d/%d memories for collection '%s'.", processed, total, coll_name)

        self._save_last_run(coll_name, now)
        self.logger.info("decay completed for collection '%s' – %d day(s) applied.", coll_name, elapsed_days)
        return
        
