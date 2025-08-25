from src.user_database import UserDatabase
from src.vector_database import VectorDataBase

class MemoryDatabases:
    short_term: VectorDataBase
    long_term: VectorDataBase
    users: UserDatabase

    def __init__(self, short: VectorDataBase, long: VectorDataBase, users: UserDatabase)-> None:
        self.short_term = short
        self.long_term = long
        self.users = users
        return

