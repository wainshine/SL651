"""水位站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import VoltageGenerator, WaterLevelGenerator


class WaterLevelStation(BaseStation):
    """水位站。上报: 瞬时河道水位 + 电池电压。"""

    DEVICE_TYPE = "水位站"
    STATION_TYPE = 0x48  # 河道

    def __init__(self, station_addr: str, base_level: float = 5.0) -> None:
        super().__init__(station_addr)
        self.water_gen = WaterLevelGenerator(base_level=base_level)
        self.voltage_gen = VoltageGenerator()
        self._last_report_level = None

    def check_alert_trigger(self, threshold: float = 0.05) -> bool:
        current = self.water_gen.current
        if self._last_report_level is None:
            self._last_report_level = current
            return False
        if abs(current - self._last_report_level) >= threshold:
            self._last_report_level = current
            return True
        return False

    def generate_elements(self) -> list[tuple[int, float, int, int]]:
        return [
            (0x39, self.water_gen.next(self.tick), 4, 3),   # 瞬时河道水位 N(7,3)
            (0x38, self.voltage_gen.next(), 2, 2),           # 电池电压
        ]
