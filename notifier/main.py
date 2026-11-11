import asyncio
import logging
import signal
import sys

from notifier.config import load_notifier_config, sync_config
from notifier.database import DatabaseConnection
from notifier.database.credential_migration import migrate_credentials
from notifier.services.evaluator import Evaluator


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
# HTTPX logs full webhook URLs at INFO; HTTP transport diagnostics contain secrets.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run():
    config = load_notifier_config()
    connection = DatabaseConnection()
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def _signal_handler():
        logger.info("Shutdown signal received — stopping notifier gracefully")
        shutdown_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _signal_handler)
    else:
        # asyncio cannot register signal handlers on Windows.
        def _win_handler(signum, frame):
            _signal_handler()

        signal.signal(signal.SIGTERM, _win_handler)
        signal.signal(signal.SIGINT, _win_handler)

    try:
        async with connection.connect() as session:
            async with session.begin():
                await migrate_credentials(session)
            await sync_config(session, config)
        logger.info("Notifier iniciado — %d regra(s) sincronizada(s)", len(config.rules))

        evaluator = Evaluator(shutdown_event=shutdown_event)
        await evaluator.run_forever(connection.connect)
    finally:
        await connection.close()
        logger.info("Notifier encerrado")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
