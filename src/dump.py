import json
import os

from src.config import Config
from src.db_bundle import DbBundle


def dump_all_dbs(bundle: DbBundle, conf: Config)-> None:
    obj = {
        "stm": [],
        "ltm": [],
        "users": [],
    }

    for coll_name in bundle.short_term.get_collection_names():
        mems = bundle.short_term.peek_oldest(coll_name, None)
        obj["stm"].append({
            "coll": coll_name,
            "mems": [x.to_dict() for x in mems]
        })
    
    for coll_name in bundle.long_term.get_collection_names():
        mems = bundle.long_term.peek_oldest(coll_name, None)
        obj["ltm"].append({
            "coll": coll_name,
            "mems": [x.to_dict() for x in mems]
        })
    
    for coll_name in bundle.users.get_collaction_names():
        coll_obj = {"coll": coll_name, "users": []}
        for user in bundle.users.get_collection_users(coll_name):
            mems = bundle.users.query(coll_name, user, n=conf.user_db.max_size_per_user + 1)
            coll_obj["users"].append({
                "user": user,
                "mems": [x.to_dict() for x in mems]
            })
        obj["users"] = coll_obj
    
    with open("dump.json", "w+", encoding="utf-8") as f:
        json.dump(obj, f)
    
    os.startfile("dump.json")
