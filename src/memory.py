import json
import uuid
from typing import Self


class Memory:
    id: str
    user: str | None
    content: str
    time: int

    def __init__(self, id: str = "", content: str = "", time: int = 0, user: str | None = None):
        self.id = id
        self.content = content
        self.time = time
        self.user = user
        return
    
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
