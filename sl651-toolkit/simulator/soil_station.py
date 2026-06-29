"""墒情站模拟器。"""

from __future__ import annotations

from .base_station import BaseStation
from .generators import SoilMoistureGenerator, VoltageGenerator


class SoilStation(BaseStation):
    """墒情站模拟器。

    上报要素：
    - 0600~0603: 10/20/30/40cm 土壤含水量
    - 0610~0613: 10/20/30/40cm 土壤温度
    - 0800: 电源电压
    """

    DEVICE_TYPE = "soil"

    def __init__(
        self,
        station_addr: str,
        center_addr: str = "01",
        password: str = "1234",
    ) -> None:
        super().__init__(station_addr, center_addr, password)
        self.soil_gen = SoilMoistureGenerator()
        self.voltage_gen = VoltageGenerator()

    def generate_elements(self) -> list[tuple[str, object]]:
        moisture, temps = self.soil_gen.next()
        voltage = self.voltage_gen.next()

        elements: list[tuple[str, object]] = []
        # 4 层含水量
        moisture_ids = ["0600", "0601", "0602", "0603"]
        for i, m in enumerate(moisture[:4]):
            elements.append((moisture_ids[i], m))
        # 4 层温度
        temp_ids = ["0610", "0611", "0612", "0613"]
        for i, t in enumerate(temps[:4]):
            elements.append((temp_ids[i], t))
        # 电压
        elements.append(("0800", voltage))
        return elements

    def add_rain(self, intensity: float) -> None:
        """注入降雨影响（与雨量站联动时使用）。"""
        self.soil_gen.add_rain(intensity)
