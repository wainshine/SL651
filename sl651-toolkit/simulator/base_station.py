"""遥测站设备模拟器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStation(ABC):
    """遥测站模拟器基类。"""

    DEVICE_TYPE: str = ""
    STATION_TYPE: int = 0x48  # 默认河道站

    def __init__(self, station_addr: str, station_type: int | None = None) -> None:
        self.station_addr = station_addr
        if len(station_addr) != 10 or any(
            c not in "0123456789abcdefABCDEF" for c in station_addr
        ):
            raise ValueError(f"station_addr 必须为 10 位十六进制字符串，当前: {station_addr!r}")
        self.station_addr_hex = station_addr
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
