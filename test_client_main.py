import asyncio
import json
import os
import time
import uuid

from client_libs.python.memento import Memento, DbEnum, Memory, OpenLlmMsg

message_types = ["store", "query", "evict", "process", "count", "clear", "close"]
msg_type_inp_question = f"\nmsg type ({', '.join(message_types)}): "


# needed since standard input blocks thread and leads to ping timeout
async def async_input(text: str = "") -> str:
    return await asyncio.to_thread(input, text)


db_map = {
    "stm": DbEnum.SHORT_TERM,
    "ltm": DbEnum.LONG_TERM,
    "users": DbEnum.USERS,
}


async def main():
    global db_map

    client = Memento(
        abs_dir=os.path.realpath("."),
    )
        
    while True:
        inp = await async_input(msg_type_inp_question)
        match inp:
            case "store":
                content = await async_input("content: ")

                user = await async_input("user (or empty): ")
                user = None if user == "" else user
                score = float(await async_input("score: "))
                lifetime = int(await async_input("lifetime: "))

                ai_name = await async_input("ai name: ")
                to = await async_input("store to (stm, ltm, users): ")

                await client.store(
                    memories=[
                        Memory.from_dict({
                            "id": str(uuid.uuid4()),
                            "content": content,
                            "user": user,
                            "time": int(time.time() * 1_000),
                            "score": score,
                            "lifetime": lifetime,
                        }),
                    ],
                    collection_name=ai_name,
                    to=[db_map[to]]
                )

            case "query":
                query = await async_input("query: ")

                user = await async_input("user (or empty): ")
                user = None if user == "" else user

                ai_name = await async_input("ai name: ")

                from_ = await async_input("query from (stm, ltm, users): ")
                n = int(await async_input("n: "))

                result = await client.query(
                    query_str=query,
                    collection_name=ai_name,
                    user=user,
                    from_=[db_map[from_]],
                    n=[n],
                    timeout=2.0,
                )

                print("Query response:")
                if len(result.short_term) > 0:
                    print("short:", [x.to_dict() for x in result.short_term])
                if len(result.long_term) > 0:
                    print("long:", [x.to_dict() for x in result.long_term])
                if len(result.users) > 0:
                    print("users:", [x.to_dict() for x in result.users])

            case "evict":
                ai_name = await async_input("ai name: ")

                await client.evict(
                    collection_name=ai_name,
                )

            case "process":
                ai_name = await async_input("ai name: ")
                context = None
                with open("./example_client/conversation.json", "r", encoding="utf-8") as f:
                    messages = json.load(f)
                
                await client.process(
                    collection_name=ai_name,
                    context=context,
                    messages=[OpenLlmMsg(**x) for x in messages["convo"]],
                )
            
            case "count":
                ai_name = await async_input("ai name: ")
                from_ = await async_input("count from (stm, ltm, both): ")
                frm = []
                if from_.lower() in ("stm", "ltm"):
                    frm = [from_.lower()]
                elif from_.lower() in ("both", "all"):
                    frm = ["stm", "ltm"]
                else:
                    frm = ["stm", "ltm"]
                
                await client.count(
                    collection_name=ai_name,
                    from_=[db_map[x] for x in frm],
                    timeout=2_000,
                )
            
            case "clear":
                ai_name = await async_input("ai name: ")
                target = await async_input("clear target (stm, ltm, users): ")
                target = target if target in ("stm", "ltm", "users") else "stm"

                user_val = None
                if target == "users":
                    u = await async_input("user (empty = ALL users): ")
                    user_val = None if u == "" else u

                confirm = (await async_input("WARNING: This action permanently deletes data. Type 'confirm' to proceed: ")).strip().lower()
                if confirm != "confirm":
                    print("Clear aborted.")
                    continue

                await client.clear(
                    collection_name=ai_name,
                    target=db_map[target],
                    user=user_val,
                )

            case "close":
                await client.close()
                exit(0)
                    


if __name__ == "__main__":
    asyncio.run(main())
