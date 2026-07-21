import httpx

from notifier.channels.base import Alert, SEVERITY_COLOR


class DiscordChannel:
    name = "discord"

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    async def send(self, alert: Alert) -> None:
        payload = {
            "embeds": [
                {
                    "title": f"[{alert.severity.upper()}] {alert.rule}",
                    "description": f"{alert.entity}: {alert.message} "
                                   f"(valor: {alert.value:g}, threshold: {alert.threshold:g})",
                    "color": int(SEVERITY_COLOR.get(alert.severity, "808080"), 16),
                }
            ]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self._webhook_url, json=payload)
            response.raise_for_status()
