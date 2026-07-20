import asyncio
import os
import socket

from app.config import get_settings
from app.db.postgres import PostgresStore
from app.integrations.processor import IntegrationEventProcessor
from app.integrations.delivery_processor import DeliveryProcessor
from app.integrations.vault import IntegrationCredentialVault


async def main() -> None:
    settings = get_settings()
    store = PostgresStore(settings)
    await store.connect()
    processor = IntegrationEventProcessor(store, f"integration-worker:{socket.gethostname()}")
    delivery_processor = DeliveryProcessor(store, IntegrationCredentialVault(settings), f"integration-worker:{socket.gethostname()}")
    poll_seconds = max(1.0, float(os.getenv("INTEGRATION_WORKER_POLL_SECONDS", "2")))
    try:
        while True:
            result = await processor.process_next()
            delivery_result = await delivery_processor.process_next()
            if result is None and delivery_result is None:
                await asyncio.sleep(poll_seconds)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
