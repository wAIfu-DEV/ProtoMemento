import asyncio
import json
import sys
import time
import uuid

from websockets.asyncio.client import connect, ClientConnection


async def recv_routine(ws: ClientConnection):
    while True:
        await asyncio.sleep(0)
        try:
            async with asyncio.timeout(0.5):
                data = await ws.recv(decode=True)
                print("Received: ", json.dumps(json.loads(data), indent=4))
        except:
            continue


# needed since standard input blocks thread and leads to ping timeout
async def async_input(text: str = "") -> str:
    return await asyncio.to_thread(input, text)


async def main():
    async with connect(uri="ws://127.0.0.1:4286") as ws:
        
        asyncio.create_task(recv_routine(ws))
        
        while True:
            await asyncio.sleep(0)

            inp = await async_input("msg type (store, query, evict, process, close): ")
            match inp:
                case "store":
                    content = await async_input("content: ")

                    user = await async_input("user (or empty): ")
                    user = None if user == "" else user
                    score = float(await async_input("score: "))
                    lifetime = int(await async_input("lifetime: "))

                    ai_name = await async_input("ai name: ")
                    to = await async_input("store to (stm, ltm, users): ")

                    data = json.dumps({
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
                    await ws.send(data, text=True)
                case "query":
                    query = await async_input("query: ")

                    user = await async_input("user (or empty): ")
                    user = None if user == "" else user

                    ai_name = await async_input("ai name: ")

                    from_ = await async_input("query from (stm, ltm, users): ")
                    n = int(await async_input("n: "))

                    data = json.dumps({
                        "uid": str(uuid.uuid4()),
                        "type": "query",
                        "ai_name": ai_name,
                        "query": query,
                        "user": user,
                        "from": [from_],
                        "n": [n],
                    })
                    await ws.send(data, text=True)
                case "evict":
                    ai_name = await async_input("ai name: ")

                    data = json.dumps({
                        "uid": str(uuid.uuid4()),
                        "type": "evict",
                        "ai_name": ai_name,
                    })
                    await ws.send(data, text=True)
                case "process":
                    ai_name = await async_input("ai name: ")
                    context = None
                    with open("./example_client/conversation.json", "r", encoding="utf-8") as f:
                        messages = json.load(f)
                    
                    data = json.dumps({
                        "uid": str(uuid.uuid4()),
                        "type": "process",
                        "ai_name": ai_name,
                        "context": context,
                        "messages": messages["convo"]
                    })
                    await ws.send(data, text=True)
                case "close":
                    data = json.dumps({
                        "uid": str(uuid.uuid4()),
                        "type": "close",
                    })
                    await ws.send(data, text=True)
                    exit(0)
                    


if __name__ == "__main__":
    asyncio.run(main())
