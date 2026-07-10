import asyncio

from analytics.services import process_pending_native_queries


async def run():
    processed = await process_pending_native_queries()
    print(f"Processed {processed} native queries")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
