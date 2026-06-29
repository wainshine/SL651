"""SL651-2014 报文编码器。

用于构造 SL651 报文，主要供设备模拟器使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import constants as C
from .bcd import (
    bcd_bytes_to_int,
    datetime_to_bcd,
    int_to_bcd,
    int_to_bcd_bytes,
)
from .crc import crc16_bytes


class EncodeError(Exception):
    """编码异常。"""


class SL651Encoder:
    """SL651 报文编码器。

    用法::

        encoder = SL651Encoder(
            center_addr="01",
            remote_addr="1234567890",
            password="1234",
        )
        frame = encoder.build_a1_frame(
            elements=[("0040", 12.345), ("0800", 12.6)],
            body_time=datetime.now(),
        )
    """

    def __init__(
        self,
        center_addr: str = "01",
        remote_addr: str = "0000000000",
        password: str = "0000",
    ) -> None:
        """初始化编码器。

        Args:
            center_addr: 中心站地址，2 位十进制字符串（如 "01"）
            remote_addr: 遥测站地址，10 位十进制字符串（如 "1234567890"）
            password: 密码，4 位十进制字符串
        """
        if len(center_addr) != 2 or not center_addr.isdigit():
            raise EncodeError(f"中心站地址必须为 2 位数字字符串，当前: {center_addr!r}")
        if len(remote_addr) != 10 or not remote_addr.isdigit():
            raise EncodeError(f"遥测站地址必须为 10 位数字字符串，当前: {remote_addr!r}")
        if len(password) != 4 or not password.isdigit():
            raise EncodeError(f"密码必须为 4 位数字字符串，当前: {password!r}")

        self.center_addr = center_addr
        self.remote_addr = remote_addr
        self.password = password

    # ------------------------------------------------------------------
    # 帧构造
    # ------------------------------------------------------------------

    def build_frame(
        self,
        function_code: int,
        message_type: str,
        body: bytes,
        direction: int = C.DIR_UPSTREAM,
    ) -> bytes:
        """构造完整 SL651 帧。

        Args:
            function_code: 功能码（如 0x05 定时自报）
            message_type: 报文类型 2 字符（如 "A1"）
            body: 报文正文字节
            direction: 上下行标志

        Returns:
            完整帧 bytes（含起止符和 CRC）
        """
        # 构造帧头
        header = bytearray()
        header.append(int_to_bcd(int(self.center_addr)))
        for i in range(0, 10, 2):
            header.append(int_to_bcd(int(self.remote_addr[i : i + 2])))
        for i in range(0, 4, 2):
            header.append(int_to_bcd(int(self.password[i : i + 2])))
        header.append(function_code)
        header.append(direction)
        # 报文类型 1 字节 BCD
        mt_hi, mt_lo = message_type[0], message_type[1]
        header.append((int(mt_hi, 16) << 4) | int(mt_lo, 16))
        # 报文长度 2 字节 BCD
        body_len = len(body)
        header.extend(int_to_bcd_bytes(body_len, 2))

        # 计算 CRC（帧头 + 正文）
        crc = crc16_bytes(bytes(header) + body)

        # 组装完整帧
        frame = bytes([C.START_END]) + bytes(header) + body + crc + bytes([C.START_END])
        return frame

    # ------------------------------------------------------------------
    # 正文构造
    # ------------------------------------------------------------------

    def build_body(
        self,
        elements: list[tuple[str, Any]],
        body_time: datetime | None = None,
    ) -> bytes:
        """构造报文正文。

        Args:
            elements: 要素列表，每项为 (标识符, 值)
            body_time: 正文时间，None 则不带时间

        Returns:
            正文字节
        """
        body = bytearray()
        # 时间标志
        if body_time is not None:
            body.append(C.TIME_FLAG_WITH_TIME)
            body.extend(datetime_to_bcd(body_time))
        else:
            body.append(C.TIME_FLAG_NO_TIME)

        # 要素
        for identifier, value in elements:
            body.extend(self._encode_element(identifier, value))

        return bytes(body)

    def _encode_element(self, identifier: str, value: Any) -> bytes:
        """编码单个要素。"""
        element_def = C.ELEMENT_IDENTIFIERS.get(identifier)
        if element_def is None:
            raise EncodeError(f"未知要素标识符: {identifier}")

        name, unit, data_type, decimals, data_len = element_def
        # 标识符 2 字节
        id_bytes = bytes.fromhex(identifier)

        # 数据值
        if data_type == "float":
            value_bytes = self._encode_float(float(value), decimals, data_len)
        elif data_type == "int":
            value_bytes = self._encode_int(int(value), data_len)
        elif data_type == "datetime":
            value_bytes = datetime_to_bcd(value)
        elif data_type == "datetime_range":
            start, end = value
            value_bytes = datetime_to_bcd(start) + datetime_to_bcd(end)
        elif data_type == "string":
            value_bytes = self._encode_string(str(value), data_len)
        else:
            raise EncodeError(f"不支持的数据类型: {data_type}")

        if len(value_bytes) != data_len:
            raise EncodeError(
                f"要素 {identifier}({name}) 编码后长度 {len(value_bytes)} 与定义长度 {data_len} 不符"
            )

        return id_bytes + value_bytes

    @staticmethod
    def _encode_float(value: float, decimals: int, data_len: int) -> bytes:
        """浮点数 -> BCD 字节。

        负数：最高字节最高位置 1。
        """
        negative = value < 0
        abs_val = abs(value)
        scaled = round(abs_val * (10 ** decimals))
        # 转为 BCD 字符串，长度 = data_len * 2
        digits = f"{int(scaled):0{data_len * 2}d}"
        bcd = bytes(int_to_bcd(int(digits[i : i + 2])) for i in range(0, len(digits), 2))
        if negative:
            bcd = bytes([(bcd[0] | 0x80)] + list(bcd[1:]))
        return bcd

    @staticmethod
    def _encode_int(value: int, data_len: int) -> bytes:
        """整数 -> BCD 字节。"""
        negative = value < 0
        abs_val = abs(value)
        digits = f"{abs_val:0{data_len * 2}d}"
        bcd = bytes(int_to_bcd(int(digits[i : i + 2])) for i in range(0, len(digits), 2))
        if negative:
            bcd = bytes([(bcd[0] | 0x80)] + list(bcd[1:]))
        return bcd

    @staticmethod
    def _encode_string(value: str, data_len: int) -> bytes:
        """字符串 -> 定长字节（ASCII，不足补 0x00）。"""
        encoded = value.encode("ascii", errors="replace")[:data_len]
        return encoded.ljust(data_len, b"\x00")

    # ------------------------------------------------------------------
    # 常用报文快捷构造
    # ------------------------------------------------------------------

    def build_a1_frame(
        self,
        elements: list[tuple[str, Any]],
        body_time: datetime | None = None,
    ) -> bytes:
        """构造 A1 定时/自报帧。"""
        body = self.build_body(elements, body_time)
        return self.build_frame(0x05, "A1", body)

    def build_a2_frame(
        self,
        elements: list[tuple[str, Any]],
        body_time: datetime | None = None,
    ) -> bytes:
        """构造 A2 加报帧。"""
        body = self.build_body(elements, body_time)
        return self.build_frame(0x06, "A2", body)

    def build_a4_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A4 测试报帧（无要素数据）。"""
        body = self.build_body([], body_time)
        return self.build_frame(0x01, "A4", body)

    def build_a0_frame(self, body_time: datetime | None = None) -> bytes:
        """构造 A0 链路维持报（心跳）。"""
        body = self.build_body([], body_time)
        return self.build_frame(0x02, "A0", body)
