from email.message import EmailMessage

import aiosmtplib

from notifier.channels.base import Alert


class EmailChannel:
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        recipients: list[str],
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._recipients = recipients

    async def send(self, alert: Alert) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message["Subject"] = f"[PGWarden][{alert.severity.upper()}] {alert.rule} — {alert.entity}"
        message.set_content(
            f"{alert.entity}: {alert.message}\n"
            f"Valor observado: {alert.value:g}\n"
            f"Threshold: {alert.threshold:g}\n"
        )

        use_tls = self._port == 465
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            use_tls=use_tls,
            start_tls=not use_tls,
        )
