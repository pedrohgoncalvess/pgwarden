"""One-way, transactional upgrade of legacy plaintext channel credentials."""
import json

from cryptography.fernet import InvalidToken
from sqlalchemy import text

from notifier.utils import decrypt, encrypt


async def migrate_credentials(session) -> int:
    rows = await session.execute(text(
        "SELECT id, credentials FROM notifier.channel WHERE credentials IS NOT NULL FOR UPDATE"
    ))
    count = 0
    for row in rows.mappings():
        value = row["credentials"]
        try:
            decrypt(value)
            continue
        except InvalidToken:
            pass
        try:
            legacy = json.loads(value)
            if not isinstance(legacy, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise RuntimeError(
                "Cannot migrate channel credentials: check ENCRYPTION_KEY or replace the invalid credentials"
            ) from None
        await session.execute(
            text("UPDATE notifier.channel SET credentials = :credentials WHERE id = :id"),
            {"id": row["id"], "credentials": encrypt(json.dumps(legacy))},
        )
        count += 1
    return count
