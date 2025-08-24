import asyncio
#import websockets
import chromadb


client: chromadb.ClientAPI = None

async def main():
    global client

    settings = chromadb.Settings()
    settings.is_persistent = True
    settings.persist_directory = "./vectors"

    client = chromadb.Client(settings=settings)
    coll = client.get_or_create_collection("test")

    print("Count:", coll.count())
    return

if __name__ == "__main__":
    asyncio.run(main())
