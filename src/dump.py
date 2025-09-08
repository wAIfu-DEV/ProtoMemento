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
        mems = bundle.users.query(coll_name, conf.user_db.max_size_per_user + 1)
        obj["users"].append({
            "coll": coll_name,
            "mems": [x.to_dict() for x in mems]
        })
    
    with open("dump.json", "w+", encoding="utf-8") as f:
        json.dump(obj, f)
    
    os.startfile("dump.json")
