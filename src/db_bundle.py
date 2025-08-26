from src.evicting_vdb import EvictingVdb
from src.user_database import UserDatabase
from src.vector_database import VectorDataBase

class DbBundle:
    short_term: EvictingVdb
    long_term: VectorDataBase
    users: UserDatabase

    def __init__(self, short: EvictingVdb, long: VectorDataBase, users: UserDatabase)-> None:
        self.short_term = short
        self.long_term = long
        self.users = users
        return

