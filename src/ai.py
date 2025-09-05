import logging
import re
import openai

from pydantic import BaseModel, Field
from typing import List, Optional

from src.config import Config
from src.messages import OpenLlmMsg


class RememberEntry(BaseModel):
    text: str = Field(..., max_length=1000)
    user: Optional[str] = Field(default=None, max_length=80)

class EmotionState(BaseModel):
    neutral: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    sadness: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    joy: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    love: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    anger: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    fear: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    surprise: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)

class ProcessResult(BaseModel):
    summary: str = Field(..., max_length=1000)
    remember: List[RememberEntry] = Field(..., min_length=1, max_length=10)
    emotions: EmotionState = Field(...)
    emotional_intensity: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)
    importance: float = Field(..., ge=0.0, le=1.0, multiple_of=0.1)


class AI:
    config: Config
    client: openai.AsyncClient
    model_name: str
    prompt_cache: dict[str, str] = {}
    logger: logging.Logger


    def __init__(self, base_url: str | None = None, api_key: str | None = None, model_name: str = "", config: Config = None):
        self.config = config
        self.client = openai.AsyncClient(
            api_key=api_key,
            base_url=base_url,
        )
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)
        return
    

    def _get_cached_prompt(self, prompt_name: str)-> str:
        if prompt_name in self.prompt_cache:
            return self.prompt_cache[prompt_name]
        else:
            with open(f"./prompts/{prompt_name}.txt", "r", encoding="utf-8") as f:
                self.prompt_cache[prompt_name] = f.read()
            return self.prompt_cache[prompt_name]


    async def process(self, ai_name: str, context: list[OpenLlmMsg], messages: list[OpenLlmMsg])-> ProcessResult | None:
        process_prompt = self._get_cached_prompt("process")

        msg_str = ""
        for msg in messages:
            name = ""
            match msg.role:
                case "assistant": name = ai_name
                case "user":      name = msg.name if msg.name is not None else "User"
                case "system":    name = "SYSTEM"
                case _:           continue # skip any messages that aren't standard
            msg_str += f"{name}: {msg.content}\n"
        
        process_prompt = re.sub(r"\{\{char\}\}", ai_name, process_prompt)
        process_prompt = process_prompt if process_prompt.endswith("\n") else process_prompt + "\n"
        
        prompt_msg = {
            "role": "user",
            "content": f"{ process_prompt }{ msg_str.strip() }",
        }

        completion = await self.client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[*context, prompt_msg],
            temperature=self.config.openllm.temp,
            max_completion_tokens=self.config.openllm.max_completion_tokens,
            response_format=ProcessResult,
        )
        parsed = completion.choices[0].message.parsed

        self.logger.info("process result: %s", parsed.model_dump_json(indent=4))

        return parsed
        
