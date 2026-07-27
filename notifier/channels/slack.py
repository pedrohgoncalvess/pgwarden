import httpx

from notifier.channels.base import Alert


class SlackChannel:
    name = "slack"

    def __init__(self, webhook_url: str, *, client: httpx.AsyncClient | None = None):
        self._webhook_url = webhook_url
        self._client = client

    async def send(self, alert: Alert) -> None:
        if self._client is not None:
            response = await self._client.post(
                self._webhook_url,
                json={"text": alert.format_text()},
            )
            response.raise_for_status()
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._webhook_url,
                    json={"text": alert.format_text()},
                )
                response.raise_for_status()
