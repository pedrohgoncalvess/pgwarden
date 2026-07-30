"""Detect and report insecure shipped credentials."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.notifier.notification import Notification


DEFAULT_ADMIN_EMAIL = "admin@pgwarden.com"
DEFAULT_ADMIN_PASSWORD = "admin"
DEFAULT_DATABASE_USER = "postgres"
DEFAULT_DATABASE_PASSWORD = "postgres"


def get_default_credential_services(
    admin_email: str | None,
    admin_password: str | None,
    database_user: str | None,
    database_password: str | None,
) -> list[str]:
    """Return services that still use their shipped credentials."""
    services = []
    if (admin_email, admin_password) == (DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD):
        services.append("PGWarden administrator account")
    if (database_user, database_password) == (
        DEFAULT_DATABASE_USER,
        DEFAULT_DATABASE_PASSWORD,
    ):
        services.append("PostgreSQL database")
    return services


async def sync_default_credentials_notification(
    session: AsyncSession,
    admin_email: str | None,
    admin_password: str | None,
    database_user: str | None,
    database_password: str | None,
) -> None:
    """Create or resolve the security alert for shipped credentials."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('pgwarden_default_credentials'))")
    )
    result = await session.execute(
        select(Notification).where(
            Notification.hidden.is_(False),
            Notification.params["source"].astext == "security",
            Notification.params["type"].astext == "default_credentials",
        ).order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    notifications = list(result.scalars())
    services = get_default_credential_services(
        admin_email,
        admin_password,
        database_user,
        database_password,
    )
    if services:
        message = (
            "Default credentials are active for "
            f"{', '.join(services)}. Set unique credentials before production use."
        )
        params = {
            "source": "security",
            "type": "default_credentials",
            "severity": "critical",
            "services": services,
        }
        if notifications:
            notifications[0].message = message
            notifications[0].params = params
            for notification in notifications[1:]:
                notification.hidden = True
        else:
            session.add(Notification(message=message, params=params))
    elif not services:
        for notification in notifications:
            notification.hidden = True
    await session.commit()
