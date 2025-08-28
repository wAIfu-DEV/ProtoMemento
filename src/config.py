import re
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
    with open("./config.jsonc", "r", encoding="utf-8") as f:
        json_data = f.read()

    # strip comments, yup this is it, this is the jsonc parser
    json_data = re.sub(r"//.*\n", "", json_data)
    json_data = re.sub(r"/\*[^]*\*\/", "", json_data)

    return Config.model_validate_json(json_data)
