import json
import os

from src.memory import Memory
import src.utils as utils


# TODO: Currently uses JSON files for each user, might be better to use CSV
# since storing to it would just be a matter of appending to file,
# no need for the read -> parse -> modify -> stringify -> write bullshit

# TODO: Add 'collections' so that multiple client AIs don't share memory

class UserDatabase:
    size_limit_per_user: int = -1

    def __init__(self, size_limit_per_user=-1):
        if not self._is_initialized():
            self._initialize()
        self.size_limit_per_user = size_limit_per_user
        return


    def _is_initialized(self)-> bool:
        return os.path.exists("../users")


    def _initialize(self)-> None:
        os.mkdir("../users")
        return


    def _sanitize_name(self, user: str)-> str:
        return utils.sanitize_for_path(user)


    def _get_path(self, coll_name: str, user: str)-> str:
        sanitized_coll: str = self._sanitize_name(coll_name)
        sanitized_user: str = self._sanitize_name(user)
        return os.path.join("..", "users", sanitized_coll, sanitized_user + ".json")


    def _is_coll_exist(self, coll_name: str)-> bool:
        sanitized_coll: str = self._sanitize_name(coll_name)
        return os.path.exists(os.path.join("..", "users", sanitized_coll))
    
    
    def _init_coll(self, coll_name: str)-> None:
        sanitized_coll: str = self._sanitize_name(coll_name)
        path = os.path.join("..", "users", sanitized_coll)
        os.makedirs(path)


    def _is_user_exist(self, coll_name: str, user: str)-> bool:
        return os.path.exists(self._get_path(coll_name, user))


    def _read_user_file(self, coll_name: str, user: str)-> dict:
        ret: dict
        with open(self._get_path(coll_name, user), "r", encoding="utf-8") as f:
            ret = json.load(f)
        return ret
    

    def _write_user_data(self, coll_name: str, user: str, data: dict)-> None:
        with open(self._get_path(coll_name, user), "w", encoding="utf-8") as f:
            json.dump(data, f)
        return


    def _init_user(self, coll_name: str, user: str)-> None:
        with open(self._get_path(coll_name, user), "w", encoding="utf-8") as f:
            f.write('{"mems":[]}')
        return


    def store(self, coll_name: str, user: str, memory: Memory)-> None:
        if not self._is_coll_exist(coll_name):
            self._init_coll(coll_name)

        if not self._is_user_exist(coll_name, user):
            self._init_user(coll_name, user)
        
        # TODO: move all dat to superior CSV
        obj = self._read_user_file(user)

        mems: list[dict] = obj.get("mems", None)
        if not mems:
            raise AssertionError('missing field "mems" in user file.')
        
        if len(mems) > self.size_limit_per_user:
            mems = mems[len(mems) - self.size_limit_per_user:] # rem first elems
        
        mems.append(memory.to_dict())
        obj["mems"] = mems # dunno if python does hidden copies, better be safe

        self._write_user_data(user, obj)
        return


    def query(self, coll_name: str, user: str, n: int)-> list[Memory]:
        if not self._is_coll_exist(coll_name):
            return []

        if not self._is_user_exist(coll_name, user):
            return []
        
        obj = self._read_user_file(user)

        mems: list[dict] = obj.get("mems", None)
        if not mems:
            raise AssertionError('missing field "mems" in user file.')
        
        if len(mems) <= n:
            return [Memory.from_dict(x) for x in mems]
        
        mems = mems[len(mems) - n:]
        return [Memory.from_dict(x) for x in mems]
