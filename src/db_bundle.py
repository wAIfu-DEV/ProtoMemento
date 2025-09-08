
from src.config import Config
from src.vdbs.evicting_vdb import EvictingVdb
from src.vdbs.decaying_vdb import DecayingVdb
from src.user_database import UserDatabase
from src.vdbs.vdb_chroma import VdbChroma

class DbBundle:
    short_term: EvictingVdb
    long_term: DecayingVdb
    users: UserDatabase

    def __init__(self, short: EvictingVdb, long: DecayingVdb, users: UserDatabase)-> None:
        self.short_term = short
        self.long_term = long
        self.users = users
        return


def databases_init(conf: Config) -> DbBundle:
    short_size = conf.short_vdb.max_size_before_evict + 10\
                      if conf.short_vdb.progressive_eviction and conf.short_vdb.max_size_before_evict > 0\
                      else -1

    short_vdb = VdbChroma(
        db_name="short",
        size_limit=short_size,
        device=conf.short_vdb.device,
    )
    long_vdb = VdbChroma(
        db_name="long",
        size_limit=conf.long_vdb.max_size,
        device=conf.long_vdb.device,
    )

    short_evicting = EvictingVdb(
        wrapped_vdb=short_vdb,
        dest_vdb=long_vdb,
        progressive_eviction=conf.short_vdb.progressive_eviction,
        max_size_before_evict=conf.short_vdb.max_size_before_evict,
        evict_fraction=conf.compression.batch_fraction_on_breach,
        evict_min_batch=conf.compression.min_batch_on_breach,
    )
    long_decaying = DecayingVdb(wrapped_vdb=long_vdb)
    user_db = UserDatabase(size_limit_per_user=conf.user_db.max_size_per_user)
    
    return DbBundle(short=short_evicting, long=long_decaying, users=user_db)
