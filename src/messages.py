from typing import Literal, List, Optional
from pydantic import BaseModel, Field
from memory import Memory

DataBases = Literal["stm", "ltm", "users"]


class MsgQuery(BaseModel):
    type: Literal["query"] = Field(...)
    uid: str = Field(...)
    ai_name: str = Field(...)
    user: str = Field(...)
    query: str = Field(...)
    from_: List[DataBases] = Field(..., alias="from", min_length=1, max_length=3)
    n: List[int] = Field(..., min_length=1, max_length=3)

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
