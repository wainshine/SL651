"""水位站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import VoltageGenerator, WaterLevelGenerator


class WaterLevelStation(BaseStation):
    """水位站模拟器。

    上报要素：
    - 0040 瞬时水位
    - 0045 日平均水位
    - 0800 电源电压
    """

    DEVICE_TYPE = "water_level"

    def __init__(
        self,
        station_addr: str,
        center_addr: str = "01",
        password: str = "1234",
        base_level: float = 5.0,
    ) -> None:
        super().__init__(station_addr, center_addr, password)
        self.water_gen = WaterLevelGenerator(base_level=base_level)
        self.voltage_gen = VoltageGenerator()
        self._daily_sum = 0.0
        self._daily_count = 0
        self._last_day = -1

    def generate_elements(self) -> list[tuple[str, object]]:
        level = self.water_gen.next(self.tick)
        voltage = self.voltage_gen.next()

        # 日平均水位
        import time

        day = self.tick // 1440
        if self._last_day != day:
            self._daily_sum = 0.0
            self._daily_count = 0
            self._last_day = day
        self._daily_sum += level
        self._daily_count += 1
        daily_avg = round(self._daily_sum / self._daily_count, 3)

        return [
            ("0040", level),
            ("0045", daily_avg),
            ("0800", voltage),
        ]
