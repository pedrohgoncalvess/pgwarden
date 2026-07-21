from dataclasses import dataclass
from typing import Protocol


SEVERITY_EMOJI = {"critical": ":rotating_light:", "warning": ":warning:"}
SEVERITY_COLOR = {"critical": "FF0000", "warning": "FFA500"}


@dataclass(frozen=True)
class Alert:
    rule: str
    severity: str
    entity: str
    message: str
    value: float
    threshold: float
    scope: str = ""
    entity_id: int | None = None
    rule_name: str = ""
    window_minutes: float = 5.0

    def format_text(self) -> str:
        emoji = SEVERITY_EMOJI.get(self.severity, ":bell:")
        return (
            f"{emoji} *[{self.severity.upper()}] {self.rule}*\n"
            f"{self.entity}: {self.message} "
            f"(valor: {self.value:g}, threshold: {self.threshold:g})"
        )

    def format_plain(self) -> str:
        return (
            f"[{self.severity.upper()}] {self.rule} — "
            f"{self.entity}: {self.message} "
            f"(valor: {self.value:g}, threshold: {self.threshold:g})"
        )


class Channel(Protocol):
    name: str

    async def send(self, alert: Alert) -> None: ...
