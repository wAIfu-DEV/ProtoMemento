import json
import os
from typing import Literal, List, Optional
from pydantic import BaseModel, Field, field_validator

from src.memory import Memory

DataBases = Literal["stm", "ltm", "users"]
MessageTypes = Literal["query", "store", "process", "evict", "unhandled"]


class MsgQuery(BaseModel):
    type: Literal["query"] = Field(...)
    uid: str = Field(...)
    ai_name: str = Field(...)
    user: str = Field(...)
    query: str = Field(...)
    from_: List[DataBases] = Field(..., alias="from", min_length=1, max_length=3)
    n: List[int] = Field(..., min_length=1, max_length=3)
    
    @field_validator("n")
    @classmethod
    def _lens_match(cls, v, info):
        from_ = info.data.get("from_")
        if from_ is not None and len(v) != len(from_):
            raise ValueError("length of 'n' must match length of 'from'")
        return v

    class Config:
        populate_by_name = True


class MsgStore(BaseModel):
    type: Literal["store"] = Field(...)
    uid: str = Field(...)
    ai_name: str = Field(...)
    memories: List[Memory] = Field(...)
    to: List[DataBases] = Field(..., min_length=1, max_length=3)

    class Config:
        populate_by_name = True


class OpenLlmMsg(BaseModel):
    role: Literal["assistant", "user", "system"] | str = Field(...)
    content: str = Field(...)
    name: Optional[str] = Field(...)

    class Config:
        populate_by_name = True


class MsgProcess(BaseModel):
    type: Literal["process"] = Field(...)
    uid: str = Field(...)
    ai_name: str = Field(...)
    context: Optional[List[OpenLlmMsg]] = Field(...)
    messages: List[OpenLlmMsg] = Field(...)

    class Config:
        populate_by_name = True


class MsgEvict(BaseModel):
    type: Literal["evict"] = Field(...)
    uid: str = Field(...)
    ai_name: str = Field(...)

    class Config:
        populate_by_name = True


def generate_schemas()-> None:
    models: list[tuple[MessageTypes, BaseModel]] = [
        ("query", MsgQuery),
        ("store", MsgStore),
        ("process", MsgProcess),
        ("evict", MsgEvict),
    ]

    for tpl in models:
        schema = tpl[1].model_json_schema()
        with open(os.path.join(".", "schemas", tpl[0] + ".json"), "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=4)
