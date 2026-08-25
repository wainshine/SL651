"""墒情站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import SoilMoistureGenerator, VoltageGenerator


class SoilStation(BaseStation):
    """墒情站。上报: 10/20/30/40cm土壤含水量 + 电池电压。"""

    DEVICE_TYPE = "墒情站"
    STATION_TYPE = 0x4D  # 墒情

    def __init__(self, station_addr: str) -> None:
        super().__init__(station_addr)
        self.soil_gen = SoilMoistureGenerator()
        self.voltage_gen = VoltageGenerator()

    def generate_elements(self) -> list[tuple[int, float, int, int]]:
        moisture, _temps = self.soil_gen.next(self.tick)
        return [
            (0x10, moisture[0], 2, 1),  # 10cm 土壤含水量
            (0x11, moisture[1], 2, 1),  # 20cm
            (0x12, moisture[2], 2, 1),  # 30cm
            (0x13, moisture[3], 2, 1),  # 40cm
            (0x38, self.voltage_gen.next(), 2, 2),
        ]
