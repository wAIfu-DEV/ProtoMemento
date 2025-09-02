import json
import logging
from pydantic import BaseModel, Field


class WssConfig(BaseModel):
    host: str = Field("127.0.0.1")
    port: int = Field(4286)


class OpenLlmConfig(BaseModel):
    base_url: str = Field("https://api.openai.com/v1")
    model: str = Field("gpt-4o-mini")
    temp: float = Field(1.0)
    max_completion_tokens: int = Field(1000)


class ShortVdbConfig(BaseModel):
    progressive_eviction: bool = Field(True)
    max_size_before_evict: int = Field(500)


class LongVdbConfig(BaseModel):
    max_size: int = Field(5_000)
    max_memory_lifetime: int = Field(180)


class UserDbConfig(BaseModel):
    max_size_per_user: int = Field(25)
    
    
class CompressionConfig(BaseModel):
    enabled: bool = Field(True)
    score_floor_for_ltm: float = Field(0.3)        # drop STM mems with score below this before LTM
    batch_size: int = Field(32)                    # how many STM mems to compress at once
    similar_top_k: int = Field(5)                  # how many LTM neighbors to compare/merge against
    prefer_new: bool = Field(True)                 # contradictory old memories are deleted
    batch_fraction_on_breach: float = Field(1.0)   # 0.5 = evict half, 1.0 = evict all, 0.0 = overflow-only
    min_batch_on_breach: int = Field(1)            # minimum items to evict when triggered


class Config(BaseModel):
    wss: WssConfig = Field(WssConfig())
    openllm: OpenLlmConfig = Field(OpenLlmConfig())
    short_vdb: ShortVdbConfig = Field(ShortVdbConfig())
    long_vdb: LongVdbConfig = Field(LongVdbConfig())
    user_db: UserDbConfig = Field(UserDbConfig())
    compression: CompressionConfig = Field(CompressionConfig())


def parse_config()-> Config:
    conf: Config
    
    with open("./config.json", "r", encoding="utf-8") as f:
        try:
            obj = json.load(f)
            conf = Config.model_validate(obj)
        except:
            logger = logging.getLogger("config")
            logger.error("error during config file reading, will reset file")
            conf = Config()
    
    with open("./config.json", "w", encoding="utf-8") as f:
        f.write(conf.model_dump_json(indent=4))
    
    return conf
