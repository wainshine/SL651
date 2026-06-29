"""遥测站设备模拟器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStation(ABC):
    """遥测站模拟器基类。"""

    DEVICE_TYPE: str = ""
    STATION_TYPE: int = 0x48  # 默认河道站

    def __init__(self, station_addr: str, station_type: int | None = None) -> None:
        self.station_addr = station_addr
        self.station_addr_hex = station_addr if len(station_addr) == 10 else ""
        if station_type is not None:
            self.STATION_TYPE = station_type
        self.tick = 0

    @abstractmethod
    def generate_elements(self) -> list[tuple[int, float, int, int]]:
        """生成要素: [(引导符, 值, 数据字节数, 小数位数), ...]"""
        ...

    def advance(self, minutes: int = 1) -> None:
        self.tick += minutes

    @property
    def name(self) -> str:
        return self.DEVICE_TYPE
