import httpx

from notifier.channels.base import Alert, SEVERITY_COLOR


class TeamsChannel:
    name = "teams"

    def __init__(self, webhook_url: str, *, client: httpx.AsyncClient | None = None):
        self._webhook_url = webhook_url
        self._client = client

    async def send(self, alert: Alert) -> None:
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": SEVERITY_COLOR.get(alert.severity, "808080"),
            "summary": f"[{alert.severity.upper()}] {alert.rule}",
            "sections": [
                {
                    "activityTitle": f"[{alert.severity.upper()}] {alert.rule}",
                    "facts": [
                        {"name": "Entidade", "value": alert.entity},
                        {"name": "Detalhe", "value": alert.message},
                        {"name": "Valor", "value": f"{alert.value:g}"},
                        {"name": "Threshold", "value": f"{alert.threshold:g}"},
                    ],
                }
            ],
        }
        if self._client is not None:
            response = await self._client.post(self._webhook_url, json=payload)
            response.raise_for_status()
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self._webhook_url, json=payload)
                response.raise_for_status()
