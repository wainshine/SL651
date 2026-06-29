"""雨量站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import RainGenerator, VoltageGenerator


class RainStation(BaseStation):
    """雨量站模拟器。

    上报要素：
    - 0010 日雨量累计值
    - 0015 小时降雨量
    - 0012 雨强
    - 0800 电源电压
    """

    DEVICE_TYPE = "rain"

    def __init__(
        self,
        station_addr: str,
        center_addr: str = "01",
        password: str = "1234",
    ) -> None:
        super().__init__(station_addr, center_addr, password)
        self.rain_gen = RainGenerator()
        self.voltage_gen = VoltageGenerator()

    def generate_elements(self) -> list[tuple[str, object]]:
        daily, hourly, intensity = self.rain_gen.next(self.tick)
        voltage = self.voltage_gen.next()
        return [
            ("0010", daily),
            ("0015", hourly),
            ("0012", intensity),
            ("0800", voltage),
        ]

    @property
    def is_raining(self) -> bool:
        """当前是否在下雨（可用于触发加报）。"""
        return self.rain_gen.raining
