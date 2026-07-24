import asyncio
import logging

from notifier.config import load_notifier_config, sync_config
from notifier.database import DatabaseConnection
from notifier.services.evaluator import Evaluator


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run():
    config = load_notifier_config()
    connection = DatabaseConnection()

    try:
        async with connection.connect() as session:
            await sync_config(session, config)
        logger.info("Notifier iniciado — %d regra(s) sincronizada(s)", len(config.rules))

        evaluator = Evaluator()
        await evaluator.run_forever(connection.connect)
    finally:
        await connection.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
