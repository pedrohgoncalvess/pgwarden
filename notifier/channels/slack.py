import httpx

from notifier.channels.base import Alert


class SlackChannel:
    name = "slack"

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    async def send(self, alert: Alert) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self._webhook_url,
                json={"text": alert.format_text()},
            )
            response.raise_for_status()
