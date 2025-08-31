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


class Config(BaseModel):
    wss: WssConfig = Field(WssConfig())
    openllm: OpenLlmConfig = Field(OpenLlmConfig())
    short_vdb: ShortVdbConfig = Field(ShortVdbConfig())
    long_vdb: LongVdbConfig = Field(LongVdbConfig())
    user_db: UserDbConfig = Field(UserDbConfig())


def parse_config()-> Config:
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
