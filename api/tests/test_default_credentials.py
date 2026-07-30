from app.security.default_credentials import get_default_credential_services


def test_get_default_credential_services_detects_shipped_credentials() -> None:
    services = get_default_credential_services(
        "admin@pgwarden.com",
        "admin",
        "postgres",
        "postgres",
    )

    assert services == ["PGWarden administrator account", "PostgreSQL database"]


def test_get_default_credential_services_ignores_custom_credentials() -> None:
    services = get_default_credential_services(
        "admin@example.com",
        "a-long-unique-password",
        "pgwarden",
        "another-long-unique-password",
    )

    assert services == []
