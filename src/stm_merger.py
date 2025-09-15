import uuid
import logging
from typing import List
from pydantic import BaseModel, Field

from src.messages import OpenLlmMsg
from src.ai import AI
from src.config import Config
from src.memory import Memory
from src.vdbs.vector_database import VectorDataBase
from src.retry_and_timeout import with_retry_and_timeout_async


class _MergeOut(BaseModel):
    new_text: str = Field(..., max_length=2000)
    delete_ids: List[str] = Field(default_factory=list)


class StmMerger:
    def __init__(self, ai: AI, vdb: VectorDataBase, config: Config):
        self.ai = ai
        self.vdb = vdb
        self.conf = config
        self.log = logging.getLogger(self.__class__.__name__)


    def _build_merge_prompt(self, ai_name: str, new_text: str, existing: List[Memory], prefer_new: bool) -> List[dict]:
        pref = "Prefer the NEW memory when wording conflicts." if prefer_new else "Prefer the most factual/consistent wording when conflicts are minor."
        sys = (
            "[SYSTEM] Decide whether to merge a NEW short-term memory with existing ones.\n"
            f"Persona: {ai_name}.\n"
            "\n"
            "DEFAULT:\n"
            "  • DO NOT MERGE. Keep memories separate unless they clearly describe the SAME fact/event.\n"
            "\n"
            "MERGE ONLY IF ALL OF THE FOLLOWING ARE TRUE:\n"
            "  1) The existing memory is very similar to the NEW one (same entities/relationships) — not just related.\n"
            "  2) They say effectively the same thing with the same people involved.\n"
            "  3) There are no material conflicts.\n"
            "If any doubt remains, DO NOT MERGE.\n"
            "\n"
            "DELETION POLICY (RARE):\n"
            "  • Only mark an existing id for deletion if it is made irrelevant or falsified by the NEW memory after merging.\n"
            "  • Otherwise, do not delete anything.\n"
            "\n"
            f"PREFERENCE: {pref}\n"
            "\n"
            "OUTPUT:\n"
            "   Return JSON: { \"new_text\": string, \"delete_ids\": string[] }.\n"
            "   If NOT MERGING, set delete_ids = [] and set new_text EXACTLY to the NEW memory text.\n"
        )
        lst = "\n".join(f"- ({m.id}) {m.content}" for m in existing) or "- (none)"
        return [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"NEW MEMORY:\n{new_text}\n\nEXISTING CANDIDATES:\n{lst}"}
        ]


    async def merge_and_store(self, ai_name: str, new_mem: Memory, context: List[OpenLlmMsg]) -> None:
        self.log.debug("STM-MERGE start: new_mem=%s", new_mem.content)

        # 1) find similar STM neighbors
        k = max(1, int(self.conf.stm_merge.similar_top_k))
        neighbors = self.vdb.query(coll_name=ai_name, query_str=new_mem.content, n=k)
        existing = [qm.memory for qm in neighbors]

        self.log.info("STM-MERGE searching for similar mems: k=%s found=%s", k, len(existing))

        # 2) if nothing else in stm, just store
        if not existing:
            self.log.info("STM-MERGE no similar found, storing new_mem id=%s", new_mem.id)
            self.vdb.store(ai_name, new_mem)
            return

        # 3) ask the model to merge
        merge_msgs = self._build_merge_prompt(
            ai_name=ai_name,
            new_text=new_mem.content,
            existing=existing,
            prefer_new=self.conf.stm_merge.prefer_new
        )
        if context is not None:
            ctx_msgs = [x.model_dump() for x in context]
            merge_msgs = [*ctx_msgs, *merge_msgs]

        self.log.debug("STM-MERGE sending merge prompt to model. new_mem.id=%s", new_mem.id)

        maybe_comp = await with_retry_and_timeout_async(
            cr=self.ai.client.beta.chat.completions.parse,
            model=self.ai.model_name,
            messages=merge_msgs,
            temperature=self.conf.openllm.temp,
            max_completion_tokens=self.conf.openllm.max_completion_tokens,
            response_format=_MergeOut,
            timeout=65.0,
            max_retries=5,
            timeout_each=60.0,
        )

        if maybe_comp is None:
            self.log.warning("STM-MERGE model call failed, storing new_mem id=%s as-is", new_mem.id)
            self.vdb.store(ai_name, new_mem)
            return

        merged: _MergeOut = maybe_comp.choices[0].message.parsed
        self.log.info("STM-MERGE result: new_text='%s...' delete_ids=%s", merged.new_text[:80], merged.delete_ids)

        # 4) delete any obsolete memories from STM
        for mem_id in (merged.delete_ids or []):
            try:
                self.vdb.remove(ai_name, mem_id)
                self.log.info("STM-MERGE deleted obsolete mem id=%s", mem_id)
            except Exception as e:
                self.log.warning("STM-MERGE delete failed: id=%s err=%s", mem_id, e)

        # 5) store merged text as a new STM memory (keep new memories metadata)
        final_mem = Memory(
            id=str(uuid.uuid4()),
            content=merged.new_text.strip(),
            user=new_mem.user,
            time=new_mem.time,
            score=new_mem.score,
            lifetime=new_mem.lifetime,
        )
        self.vdb.store(ai_name, final_mem)
        self.log.info("STM-MERGE stored final_mem id=%s", final_mem.id)
