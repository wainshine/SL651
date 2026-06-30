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
        if len(station_addr) != 10:
            raise EncodeError(f"station_addr 必须为 10 位十六进制字符串，当前: {station_addr!r}")
        try:
            self.station_addr_bytes = bytes.fromhex(station_addr)
        except ValueError:
            raise EncodeError(f"station_addr 不是有效 hex: {station_addr!r}")
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
        ascii_mode: bool = False,
    ) -> bytes:
        """构造完整 SL651 帧。

        ascii_mode=True 时使用 SOH(01H) 起始符（ASCⅡ编码）。
        """
        now = datetime.now()
        tx_time = datetime_to_bcd(now)
        serial = self._next_serial()

        body_len = C.SERIAL_LEN + C.TX_TIME_LEN + len(body)
        ident_hi = (direction << 7) | ((body_len >> 8) & 0x7F)
        ident_lo = body_len & 0xFF

        header_body = bytearray()
        # 表11(上行): [中心][站址]; 表12(下行): [站址][中心]
        if direction == C.DIR_UPLINK:
            header_body.append(self.center_addr)
            header_body.extend(self.station_addr_bytes)
        else:
            header_body.extend(self.station_addr_bytes)
            header_body.append(self.center_addr)
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

        start_byte = C.SOH if ascii_mode else C.START_BYTE
        frame_body = bytes([start_byte, start_byte]) + bytes(header_body)
        crc = crc16(frame_body)
        header_body.append((crc >> 8) & 0xFF)
        header_body.append(crc & 0xFF)

        return bytes([start_byte, start_byte]) + bytes(header_body)

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

    def build_link_maintain_body(self) -> bytes:
        return b""

    def build_link_maintain_frame(self) -> bytes:
        return self.build_frame(0x2F, self.build_link_maintain_body())

    def build_alarm_body(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
    ) -> bytes:
        return self.build_timing_body(elements, obs_time)

    def build_alarm_frame(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
    ) -> bytes:
        return self.build_frame(0x33, self.build_alarm_body(elements, obs_time))

    def build_hourly_body(
        self,
        water_levels: list[float | None],
        inst_level: float,
        voltage: float,
        obs_time: datetime | None = None,
    ) -> bytes:
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

        body.append(0xF5)
        body.append(_make_def_byte(24, 2))
        for wl in water_levels:
            if wl is None:
                body.extend(b'\xFF\xFF')
            else:
                val = int(round(wl * 100))
                body.extend(val.to_bytes(2, 'big'))

        body.append(0x39)
        body.append(_make_def_byte(4, 3))
        body.extend(_encode_bcd(inst_level, 4, 3))

        body.append(0x38)
        body.append(_make_def_byte(2, 2))
        body.extend(_encode_bcd(voltage, 2, 2))

        return bytes(body)

    def build_hourly_frame(
        self,
        water_levels: list[float | None],
        inst_level: float,
        voltage: float,
        obs_time: datetime | None = None,
    ) -> bytes:
        return self.build_frame(0x34, self.build_hourly_body(water_levels, inst_level, voltage, obs_time))

    # ------------------------------------------------------------------
    # 下行帧（中心站 → 遥测站）
    # ------------------------------------------------------------------

    def build_query_body(self, element_guides: list[int]) -> bytes:
        """查询帧正文：列出要查询的要素引导符+定义符（数据域为空）。"""
        body = bytearray()
        for guide in element_guides:
            body.append(guide)
            body.append(_make_def_byte(0, 0))  # 查询时数据域长度为0
        return bytes(body)

    def build_query_frame(self, element_guides: list[int]) -> bytes:
        """查询要素帧（下行）。"""
        return self.build_frame(0x09, self.build_query_body(element_guides), direction=C.DIR_DOWNLINK)

    def build_set_param_body(self, params: list[tuple[int, float, int, int]]) -> bytes:
        """参数设置正文：引导符+定义符+数据值。"""
        body = bytearray()
        for guide, value, data_len, decimals in params:
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))
        return bytes(body)

    def build_set_param_frame(self, params: list[tuple[int, float, int, int]]) -> bytes:
        """参数设置帧（下行）。"""
        return self.build_frame(0x08, self.build_set_param_body(params), direction=C.DIR_DOWNLINK)

    def build_clock_sync_body(self, dt: datetime | None = None) -> bytes:
        """时钟校准正文：6 字节 BCD 时间。"""
        if dt is None:
            dt = datetime.now()
        return datetime_to_bcd(dt)

    def build_clock_sync_frame(self, dt: datetime | None = None) -> bytes:
        """时钟校准帧 (0x0C, 下行)。"""
        return self.build_frame(0x0C, self.build_clock_sync_body(dt), direction=C.DIR_DOWNLINK)

    def build_reset_body(self) -> bytes:
        """复位帧正文：空。"""
        return b""

    def build_reset_frame(self) -> bytes:
        """复位帧 (0x0D, 下行)。"""
        return self.build_frame(0x0D, self.build_reset_body(), direction=C.DIR_DOWNLINK)

    # ------------------------------------------------------------------
    # ASCⅡ 编码
    # ------------------------------------------------------------------

    def build_ascii_body(
        self,
        elements: list[tuple[str, str]],
        obs_time: datetime | None = None,
    ) -> bytes:
        """构造 ASCⅡ 编码正文。

        elements: [(ASCⅡ标识符, 值字符串), ...]
        如: [("Z", "12.345"), ("Q", "5.678"), ("VT", "12.6")]
        """
        if obs_time is None:
            obs_time = datetime.now()

        parts = []
        parts.append("F1F1")
        parts.append(self.station_addr_hex)
        parts.append(f"{self.station_type:02X}")
        parts.append("F0F0")
        parts.append(obs_time.strftime("%y%m%d%H%M"))
        for code, val in elements:
            parts.append(code)
            parts.append(val)
        parts.append("")  # 末尾空格（规约要求）

        return " ".join(parts).encode("ascii")

    def build_ascii_frame(
        self,
        elements: list[tuple[str, str]],
        obs_time: datetime | None = None,
        function_code: int = 0x32,
    ) -> bytes:
        """构造 ASCⅡ 编码帧（SOH 起始）。"""
        body = self.build_ascii_body(elements, obs_time)
        return self.build_frame(function_code, body, ascii_mode=True)
