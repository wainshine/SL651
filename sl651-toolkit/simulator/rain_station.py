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

    @property
    def is_raining(self) -> bool:
        return self.rain_gen.raining

    def generate_elements(self) -> list[tuple[int, float, int, int]]:
        daily, hourly, intensity = self.rain_gen.next(self.tick)
        return [
            (0x1F, daily, 3, 1),     # 日降水量
            (0x1A, hourly, 3, 1),    # 1小时降雨量
            (0x20, daily, 3, 1),     # 当前降水量（日起始累计，规约3.6）
            (0x26, self.rain_gen.total_accum, 3, 1),  # 降水量累计值（不归零，N(6,1)）
            (0x38, self.voltage_gen.next(), 2, 2),
        ]

    def get_alert_trigger(self) -> tuple[int, float, int, int]:
        return (0x20, self.rain_gen.daily_accum, 3, 1)
