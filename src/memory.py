import json
import uuid
from typing import Optional, Self
from pydantic import BaseModel


class Memory(BaseModel):
    id: str
    user: Optional[str]
    content: str
    time: int

    class Config:
        populate_by_name = True
    
    @staticmethod
    def from_dict(input: dict)-> Self:
        return Memory(
            id=input.get("id", uuid.uuid4()),
            content=input.get("content", ""),
            time=input.get("time", 0),
            user=input.get("user", None),
        )

    def to_dict(self)-> dict:
        return {
            "id": str(self.id),
            "user": str(self.user) if self.user else None,
            "content": str(self.content),
            "time": int(self.time),
        }

    def to_json(self)-> str:
        return json.dumps(self.to_dict())


class QueriedMemory:
    memory: Memory
    distance: float

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
