"""雨量站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import RainGenerator, VoltageGenerator


class RainStation(BaseStation):
    """雨量站。上报: 日降水量 + 1小时雨量 + 当前降水量 + 累计雨量 + 电池电压。"""

    DEVICE_TYPE = "雨量站"
    STATION_TYPE = 0x50  # 降水

    def __init__(self, station_addr: str) -> None:
        super().__init__(station_addr)
        self.rain_gen = RainGenerator()
        self.voltage_gen = VoltageGenerator()

    def generate_elements(self) -> list[tuple[int, float, int, int]]:
        daily, hourly, intensity = self.rain_gen.next(self.tick)
        return [
            (0x1F, daily, 3, 1),     # 日降水量（当日累计）
            (0x1A, hourly, 3, 1),    # 1小时降雨量
            (0x20, hourly, 3, 1),    # 当前降水量（当前小时累计）
            (0x26, daily, 3, 1),     # 累计雨量
            (0x38, self.voltage_gen.next(), 2, 2),
        ]
