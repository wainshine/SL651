"""SL651-2014 报文编码器。"""

from __future__ import annotations

from datetime import datetime

from . import constants as C
from .bcd import (
    datetime_to_bcd,
    int_to_bcd_bytes,
)
from .crc import crc16


class EncodeError(Exception):
    """编码异常。"""


def _make_def_byte(data_len: int, decimals: int = 0) -> int:
    return ((data_len & 0x1F) << 3) | (decimals & 0x07)


def _encode_bcd(value: float, data_len: int, decimals: int) -> bytes:
    """浮点数 -> BCD 编码字节。负数按 SL651 6.6.3.3 用 0xFF 前缀。"""
    negative = value < 0
    scaled = round(abs(value) * (10 ** decimals))
    if negative:
        bcd = int_to_bcd_bytes(scaled, data_len - 1)
        return b"\xFF" + bcd
    return int_to_bcd_bytes(scaled, data_len)


class SL651Encoder:
    """SL651 报文编码器。

    password 默认 0 用于测试；生产环境应使用 SL651 规范要求的非零密码。
    """

    def __init__(
        self,
        center_addr: int = 1,
        station_addr: str = "0000000000",
        password: int = 0,
        station_type: int = 0x4B,
    ):
        self.center_addr = center_addr & 0xFF
        self.station_addr_hex = station_addr
        if len(station_addr) == 10:
            try:
                self.station_addr_bytes = bytes.fromhex(station_addr)
            except ValueError:
                raise EncodeError(f"station_addr 不是有效 hex: {station_addr!r}")
        else:
            self.station_addr_bytes = b"\x00" * 5
        self.password = password & 0xFFFF
        self.station_type = station_type & 0xFF
        self._serial = int(datetime.now().timestamp()) % 65535  # 用时间戳保证重启后不重复

    def _next_serial(self) -> int:
        self._serial = (self._serial + 1) % 65535
        return self._serial

    def build_frame(
        self,
        function_code: int,
        body: bytes,
        direction: int = C.DIR_UPLINK,
    ) -> bytes:
        """构造完整 SL651 帧。"""
        now = datetime.now()
        tx_time = datetime_to_bcd(now)
        serial = self._next_serial()

        body_len = C.SERIAL_LEN + C.TX_TIME_LEN + len(body)
        ident_hi = (direction << 7) | ((body_len >> 8) & 0x7F)
        ident_lo = body_len & 0xFF

        header_body = bytearray()
        header_body.append(self.center_addr)
        header_body.extend(self.station_addr_bytes)
        header_body.append((self.password >> 8) & 0xFF)
        header_body.append(self.password & 0xFF)
        header_body.append(function_code)
        header_body.append(ident_hi)
        header_body.append(ident_lo)
        header_body.append(C.STX)
        header_body.append((serial >> 8) & 0xFF)
        header_body.append(serial & 0xFF)
        header_body.extend(tx_time)
        header_body.extend(body)
        header_body.append(C.ETX)

        frame_body = bytes([C.START_BYTE, C.START_BYTE]) + bytes(header_body)
        crc = crc16(frame_body)
        header_body.append((crc >> 8) & 0xFF)
        header_body.append(crc & 0xFF)

        return bytes([C.START_BYTE, C.START_BYTE]) + bytes(header_body)

    def build_timing_body(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
    ) -> bytes:
        """构造上行定时报正文。

        elements: [(引导符, 值, 数据字节数, 小数位数), ...]
        """
        if obs_time is None:
            obs_time = datetime.now()
        ot = datetime_to_bcd(obs_time)[:5]

        body = bytearray()
        body.append(0xF1)
        body.append(0xF1)
        body.extend(self.station_addr_bytes)
        body.append(self.station_type)
        body.append(0xF0)
        body.append(0xF0)
        body.extend(ot)

        for guide, value, data_len, decimals in elements:
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))

        return bytes(body)

    def build_timing_frame(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
        function_code: int = 0x32,
    ) -> bytes:
        body = self.build_timing_body(elements, obs_time)
        return self.build_frame(function_code, body)
