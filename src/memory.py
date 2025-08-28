import json
import uuid
from typing import Optional, Self
from pydantic import BaseModel, Field


class Memory(BaseModel):
    id: str = Field(...)
    content: str = Field(...)
    time: int = Field(...)

    user: Optional[str] = Field(...)
    score: Optional[float] = Field(...)
    lifetime: Optional[int] = Field(...)

    class Config:
        populate_by_name = True
    

    @staticmethod
    def from_dict(input: dict)-> Self:
        return Memory(
            id=input.get("id", uuid.uuid4()),
            content=input.get("content", ""),
            time=input.get("time", 0),
            user=input.get("user", None),
            score=input.get("score", None),
            lifetime=input.get("lifetime", None),
        )

    def to_dict(self)-> dict:
        obj = {
            "id": str(self.id),
            "content": str(self.content),
            "time": int(self.time),
        }

        if not self.user is None:
            obj["user"] = str(self.user)
        if not self.score is None:
            obj["score"] = float(self.score)
        if not self.lifetime is None:
            obj["lifetime"] = int(self.lifetime)
        return obj

    def to_json(self)-> str:
        return json.dumps(self.to_dict())


class QueriedMemory:
    memory: Memory = Field(...)
    distance: float = Field(...)

    def __init__(self, memory: Memory = None, distance: float = 0.0):
        self.memory = memory
        self.distance = distance
        return

    def to_dict(self)-> dict:
        return {
            "memory": self.memory.to_json(),
            "distance": float(self.distance),
        }
    
    def to_json(self)-> str:
        return json.dumps(self.to_dict())
