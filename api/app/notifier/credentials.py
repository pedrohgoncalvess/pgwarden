from urllib.parse import urlsplit


def validate_credentials(name: str, credentials: dict) -> None:
    """Validate a complete replacement without including secrets in errors."""
    if name in {"slack", "discord", "teams"}:
        if set(credentials) != {"webhook_url"}:
            raise ValueError("A complete webhook_url is required")
        value = credentials["webhook_url"]
        try:
            url = urlsplit(value) if isinstance(value, str) else None
            valid = url and url.scheme == "https" and url.hostname and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid or any(char.isspace() for char in value):
            raise ValueError("webhook_url must be a complete HTTPS URL without user information")
        return
    if name != "email":
        raise ValueError("Unsupported notification channel")
    if set(credentials) != {"host", "port", "username", "password", "from", "to"}:
        raise ValueError("Replace all SMTP fields: host, port, username, password, from, to")
    for key in ("host", "from"):
        if not isinstance(credentials[key], str) or not credentials[key].strip():
            raise ValueError("SMTP host and from are required")
    port = credentials["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("SMTP port must be an integer between 1 and 65535")
    username, password = credentials["username"], credentials["password"]
    if not isinstance(username, str) or not isinstance(password, str) or bool(username) != bool(password):
        raise ValueError("Provide both SMTP username and password, or leave both empty")
    recipients = credentials["to"]
    if isinstance(recipients, str):
        recipients = recipients.split(",")
    if not isinstance(recipients, list) or not recipients or any(
        not isinstance(item, str) or not item.strip() for item in recipients
    ):
        raise ValueError("At least one SMTP recipient is required")
