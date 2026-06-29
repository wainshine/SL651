"""遥测站设备模拟器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from sl651 import SL651Encoder
from sl651.constants import DEVICE_TYPES


class BaseStation(ABC):
    """遥测站模拟器基类。"""

    DEVICE_TYPE: str = ""

    def __init__(
        self,
        station_addr: str,
        center_addr: str = "01",
        password: str = "1234",
    ) -> None:
        """初始化设备。

        Args:
            station_addr: 遥测站地址，10 位数字字符串
            center_addr: 中心站地址，2 位数字字符串
            password: 密码，4 位数字字符串
        """
        if not hasattr(self, "DEVICE_TYPE") or not self.DEVICE_TYPE:
            raise ValueError("子类必须设置 DEVICE_TYPE")
        self.device_type = self.DEVICE_TYPE
        self.device_info = DEVICE_TYPES[self.device_type]
        self.station_addr = station_addr
        self.encoder = SL651Encoder(
            center_addr=center_addr,
            remote_addr=station_addr,
            password=password,
        )
        self.tick = 0  # 时间步进（分钟）

    @abstractmethod
    def generate_elements(self) -> list[tuple[str, object]]:
        """生成当前时刻的要素数据列表，每项为 (标识符, 值)。"""

    def build_a1_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A1 定时自报帧。"""
        elements = self.generate_elements()
        return self.encoder.build_a1_frame(elements, body_time)

    def build_a2_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A2 加报帧。"""
        elements = self.generate_elements()
        return self.encoder.build_a2_frame(elements, body_time)

    def build_a4_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A4 测试帧。"""
        return self.encoder.build_a4_frame(body_time)

    def build_a0_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A0 心跳帧。"""
        return self.encoder.build_a0_frame(body_time)

    def advance(self, minutes: int = 1) -> None:
        """推进时间步进。"""
        self.tick += minutes

    @property
    def name(self) -> str:
        return self.device_info["name"]
