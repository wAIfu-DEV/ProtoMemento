import asyncio
import json
import sys
import time
import uuid

from websockets.asyncio.client import connect, ClientConnection

send_time = 0
repeat_obj = {}

def recv_routine(ws: ClientConnection):
    asyncio.run(recv_routine_wrapped(ws))

async def recv_routine_wrapped(ws: ClientConnection):
    while True:
        try:
            async with asyncio.timeout(0.5):
                data = await ws.recv(decode=True)
                print("client-side latency: ", int(time.time() * 1_000) - send_time, "ms")
                print("Received: ", json.dumps(json.loads(data), indent=4))
                print("\nmsg type (store, query, evict, process, close): ", end="", flush=True)
        except:
            continue


# needed since standard input blocks thread and leads to ping timeout
async def async_input(text: str = "") -> str:
    return await asyncio.to_thread(input, text)


async def send(ws: ClientConnection, obj: dict)-> None:
    global repeat_obj, send_time
    repeat_obj = obj
    data = json.dumps(obj)
    await ws.send(data, text=True)
    send_time = int(time.time() * 1_000)


async def main():
    global repeat_obj

    async with connect(uri="ws://127.0.0.1:4286") as ws:
        
        asyncio.create_task(asyncio.to_thread(recv_routine, ws))
        
        while True:
            inp = await async_input("msg type (store, query, evict, process, close, repeat): ")
            match inp:
                case "store":
                    content = await async_input("content: ")

                    user = await async_input("user (or empty): ")
                    user = None if user == "" else user
                    score = float(await async_input("score: "))
                    lifetime = int(await async_input("lifetime: "))

                    ai_name = await async_input("ai name: ")
                    to = await async_input("store to (stm, ltm, users): ")

                    await send(ws, {
                        "uid": str(uuid.uuid4()),
                        "type": "store",
                        "ai_name": ai_name,
                        "memories": [
                            {
                                "id": str(uuid.uuid4()),
                                "content": content,
                                "user": user,
                                "score": score,
                                "lifetime": lifetime,
                                "time": int(time.time() * 1_000)
                            }
                        ],
                        "to": [to],
                    })
                case "query":
                    query = await async_input("query: ")

                    user = await async_input("user (or empty): ")
                    user = None if user == "" else user

                    ai_name = await async_input("ai name: ")

                    from_ = await async_input("query from (stm, ltm, users): ")
                    n = int(await async_input("n: "))

                    await send(ws, {
                        "uid": str(uuid.uuid4()),
                        "type": "query",
                        "ai_name": ai_name,
                        "query": query,
                        "user": user,
                        "from": [from_],
                        "n": [n],
                    })
                case "evict":
                    ai_name = await async_input("ai name: ")

                    await send(ws, {
                        "uid": str(uuid.uuid4()),
                        "type": "evict",
                        "ai_name": ai_name,
                    })
                case "process":
                    ai_name = await async_input("ai name: ")
                    context = None
                    with open("./example_client/conversation.json", "r", encoding="utf-8") as f:
                        messages = json.load(f)
                    
                    await send(ws, {
                        "uid": str(uuid.uuid4()),
                        "type": "process",
                        "ai_name": ai_name,
                        "context": context,
                        "messages": messages["convo"]
                    })
                case "close":
                    await send(ws, {
                        "uid": str(uuid.uuid4()),
                        "type": "close",
                    })
                    exit(0)
                case "repeat":
                    repeat_obj["uid"] = str(uuid.uuid4())

                    if "memories" in repeat_obj:
                        for m in repeat_obj["memories"]:
                            m["id"] = str(uuid.uuid4())

                    await send(ws, repeat_obj)
                    


if __name__ == "__main__":
    asyncio.run(main())
