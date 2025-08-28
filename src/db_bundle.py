from src.vdbs.vector_database import VectorDataBase
from src.vdbs.evicting_vdb import EvictingVdb
from src.vdbs.decaying_vdb import DecayingVdb
from src.user_database import UserDatabase

class DbBundle:
    short_term: EvictingVdb
    long_term: DecayingVdb
    users: UserDatabase

    def __init__(self, short: EvictingVdb, long: DecayingVdb, users: UserDatabase)-> None:
        self.short_term = short
        self.long_term = long
        self.users = users
        return

