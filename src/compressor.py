import time
import uuid
import logging
import asyncio
from math import floor
from typing import List
from pydantic import BaseModel, Field

from src.ai import AI
from src.config import Config
from src.memory import Memory
from src.vdbs.vector_database import VectorDataBase


class _CompressItem(BaseModel):
    text: str = Field(..., max_length=2000)
    source_ids: List[str] = Field(..., min_length=1, max_length=64)


class _CompressOut(BaseModel):
    memories: List[_CompressItem] = Field(..., min_length=1, max_length=50)


class _MergeOut(BaseModel):
    new_text: str = Field(..., max_length=2000)
    delete_ids: List[str] = Field(default_factory=list)


class Compressor:
    def __init__(self, ai: AI, long_vdb: VectorDataBase, config: Config):
        self.ai = ai
        self.long_vdb = long_vdb
        self.conf = config
        self.log = logging.getLogger(self.__class__.__name__)


    def _now_ms(self) -> int:
        return int(time.time() * 1000)


    def _score_mean(self, mems: List[Memory]) -> float:
        vals = [m.score for m in mems if m.score is not None]
        if not vals:
            return 0.6
        s = sum(vals) / len(vals)
        return max(0.0, min(1.0, float(s)))


    def _lifetime_from_score(self, score: float) -> int:
        return floor(score * self.conf.long_vdb.max_memory_lifetime)


    def _build_batch_prompt(self, ai_name: str, items: List[Memory]) -> dict:
        header = (
            "[SYSTEM] You are compressing short-term memories into long-term memories for "
            f"{ai_name}. Write in {ai_name}'s first person. Output concise, self-contained "
            "memories that keep the important details and drop trivial/duplicate lines. "
            "Do not invent facts.\n\n"
            'Return JSON with field "memories": { "text": string, "source_ids": string[] }[]. '
            "Group related lines together into one memory where appropriate. "
            "For each output memory, populate source_ids with the IDs of the short-term memories you actually used."
        )
        bullets = []
        for m in items:
            meta = []
            if m.score is not None:
                meta.append(f"score={m.score:.2f}")
            if m.user is not None:
                meta.append(f"user={m.user}")
            meta_str = f"[{', '.join(meta)}] " if meta else ""
            # include the id so the model can reference it
            bullets.append(f"- (id={m.id}) {meta_str}{m.content}")
        body = "\n".join(bullets) if bullets else "- (none)"
        prompt = {"role": "user", "content": header + "\n\n[INPUT]\n" + body}
        self.log.debug("compress_batch prompt >>>\n%s", prompt["content"])
        return prompt


    def _build_merge_prompt(self, ai_name: str, new_text: str, existing: List[Memory], prefer_new: bool) -> List[dict]:
        rule_pref = "Prefer the NEW memory" if prefer_new else "Prefer whichever is more factual/consistent"
        sys = (
            "[SYSTEM] Deduplicate and reconcile long-term memories.\n"
            f"Persona: {ai_name}.\n"
            f"Rules:\n"
            f"1) {rule_pref}.\n"
            "2) If an existing memory is essentially the same event/meaning, merge its missing useful details into the new memory, "
            "   and mark that existing memory for deletion.\n"
            "3) If an existing memory contradicts the new one, mark it for deletion and do NOT adopt its facts.\n"
            "4) Keep the final memory concise and self-contained in first person.\n"
            'Return JSON with fields: new_text (string), delete_ids (string[]).'
        )
        lst = "\n".join(f"- ({m.id}) {m.content}" for m in existing) or "- (none)"
        msgs = [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"NEW MEMORY:\n{new_text}\n\nEXISTING CANDIDATES:\n{lst}"}
        ]
        self.log.debug("merge prompt >>>\n%s\n\n%s", msgs[0]["content"], msgs[1]["content"])
        return msgs


    async def compress_batch_async(self, ai_name: str, stm_batch: List[Memory]) -> None:
        self.log.info("compress_batch_async start: coll=%s size=%d", ai_name, len(stm_batch))

        floor_val = self.conf.compression.score_floor_for_ltm
        filtered = [m for m in stm_batch if (m.score if m.score is not None else 0.0) >= floor_val]
        self.log.info("compress_batch_async filter: floor=%.2f -> kept=%d dropped=%d",
                      floor_val, len(filtered), len(stm_batch)-len(filtered))
        if not filtered:
            self.log.info("compress_batch_async abort: nothing above floor.")
            return

        by_id = {m.id: m for m in filtered}
        comp_msg = self._build_batch_prompt(ai_name, filtered)

        # LLM call off the loop
        comp = await asyncio.to_thread(
            self.ai.client.beta.chat.completions.parse,
            model=self.ai.model_name,
            messages=[comp_msg],
            temperature=self.conf.openllm.temp,
            max_completion_tokens=min(1000, self.conf.openllm.max_completion_tokens),
            response_format=_CompressOut,
        )
        out: _CompressOut = comp.choices[0].message.parsed
        self.log.info("compress_batch_async LLM parsed <<< %s", out.model_dump_json(indent=2))
        if not out or not out.memories:
            self.log.info("compress_batch_async abort: LLM returned no memories.")
            return

        fallback_score = self._score_mean(filtered)

        for idx, item in enumerate(out.memories, start=1):
            new_text = item.text.strip()
            contributing = [by_id[sid] for sid in (item.source_ids or []) if sid in by_id]
            score = self._score_mean(contributing) if contributing else fallback_score
            lifetime = self._lifetime_from_score(score)
            self.log.info("merge step: %d/%d (sources=%d score=%.2f life=%d)",
                          idx, len(out.memories), len(contributing), score, lifetime)

            existing_q = self.long_vdb.query(
                coll_name=ai_name,
                query_str=new_text,
                n=self.conf.compression.similar_top_k
            )
            existing = [qm.memory for qm in existing_q]
            self.log.info("similar@ltm: k=%d -> ids=%s", self.conf.compression.similar_top_k, [m.id for m in existing])

            merge_msgs = self._build_merge_prompt(ai_name, new_text, existing, self.conf.compression.prefer_new)

            # Second LLM call off the loop
            merged = (await asyncio.to_thread(
                self.ai.client.beta.chat.completions.parse,
                model=self.ai.model_name,
                messages=merge_msgs,
                temperature=self.conf.openllm.temp,
                max_completion_tokens=min(1000, self.conf.openllm.max_completion_tokens),
                response_format=_MergeOut,
            )).choices[0].message.parsed
            self.log.info("merge LLM parsed <<< %s", merged.model_dump_json(indent=2))

            for mem_id in (merged.delete_ids or []):
                try:
                    self.long_vdb.remove(ai_name, mem_id)
                    self.log.info("ltm delete: id=%s", mem_id)
                except Exception as e:
                    self.log.warning("ltm delete failed: id=%s err=%s", mem_id, e)

            mem = Memory(
                id=str(uuid.uuid4()),
                content=merged.new_text.strip(),
                user=None,
                time=self._now_ms(),
                score=score,
                lifetime=lifetime
            )
            self.long_vdb.store(ai_name, mem)
            self.log.info('ltm store: id=%s score=%.2f life=%d content="%s"',
                          mem.id, score, lifetime, mem.content[:120].replace("\n"," "))

        self.log.info("compress_batch_async done: coll=%s", ai_name)
