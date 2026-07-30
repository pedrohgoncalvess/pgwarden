import asyncio

from analytics.database import DatabaseConnection
from analytics.services.runs import run_analytics_loop


async def run():
    try:
        await run_analytics_loop()
    finally:
        await DatabaseConnection.shutdown()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
