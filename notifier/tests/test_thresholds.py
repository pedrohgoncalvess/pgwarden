import pytest

from notifier.config import Threshold


class TestThresholdAbove:
    threshold = Threshold(warning=85.0, critical=95.0, direction="above")

    @pytest.mark.parametrize(
        "value,expected",
        [
            (50.0, None),
            (84.9, None),
            (85.0, "warning"),
            (90.0, "warning"),
            (94.9, "warning"),
            (95.0, "critical"),
            (100.0, "critical"),
        ],
    )
    def test_severity_for(self, value, expected):
        assert self.threshold.severity_for(value) == expected


class TestThresholdBelow:
    threshold = Threshold(warning=0.95, critical=0.90, direction="below")

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.99, None),
            (0.96, None),
            (0.95, "warning"),
            (0.92, "warning"),
            (0.91, "warning"),
            (0.90, "critical"),
            (0.50, "critical"),
        ],
    )
    def test_severity_for(self, value, expected):
        assert self.threshold.severity_for(value) == expected
