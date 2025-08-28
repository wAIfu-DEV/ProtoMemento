import re
from jsonc_parser.parser import JsoncParser
from pydantic import BaseModel, Field


class WssConfig(BaseModel):
    host: str = Field(...)
    port: int = Field(...)


class OpenLlmConfig(BaseModel):
    base_url: str = Field(...)
    model: str = Field(...)
    temp: float = Field(...)
    max_completion_tokens: int = Field(...)


class ShortVdbConfig(BaseModel):
    progressive_eviction: bool = Field(...)
    max_size_before_evict: int = Field(...)


class LongVdbConfig(BaseModel):
    max_size: int = Field(...)


class UserDbConfig(BaseModel):
    max_size_per_user: int = 100


class Config(BaseModel):
    wss: WssConfig = Field(...)
    openllm: OpenLlmConfig = Field(...)
    short_vdb: ShortVdbConfig = Field(...)
    long_vdb: LongVdbConfig = Field(...)
    user_db: UserDbConfig = Field(...)


def parse_config()-> Config:
    obj = JsoncParser.parse_file("./config.jsonc")
    return Config.model_validate(obj)
