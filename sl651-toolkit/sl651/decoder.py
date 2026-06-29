"""SL651-2014 报文解码器。

支持解析完整帧结构、提取报文头信息、解析要素数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import constants as C
from .bcd import (
    bcd_bytes_to_int,
    bcd_to_datetime,
    bcd_to_int,
    bytes_to_hex,
    bytes_to_hex_compact,
)
from .crc import crc16, crc16_bytes


@dataclass
class ElementValue:
    """单个要素解析结果。"""

    identifier: str  # 4 位十六进制字符串，如 "0040"
    name: str
    unit: str
    data_type: str
    decimals: int
    raw_value: Any  # 解析后的原始值（float/int/datetime/str）
    raw_bytes: bytes  # 数据值原始字节

    @property
    def display_value(self) -> str:
        """带单位的展示值。"""
        if self.data_type == "float":
            return f"{self.raw_value:.{self.decimals}f} {self.unit}".strip()
        if self.data_type == "int":
            return f"{self.raw_value} {self.unit}".strip()
        if self.data_type == "datetime":
            return self.raw_value.strftime("%Y-%m-%d %H:%M:%S")
        if self.data_type == "datetime_range":
            start, end = self.raw_value
            return f"{start.strftime('%Y-%m-%d %H:%M:%S')} ~ {end.strftime('%Y-%m-%d %H:%M:%S')}"
        return str(self.raw_value)


@dataclass
class DecodedMessage:
    """SL651 报文解析结果。"""

    # ===== 帧头信息 =====
    center_station_addr: str  # 中心站地址（2 位十进制字符串）
    remote_station_addr: str  # 遥测站地址（10 位十进制字符串）
    password: str  # 密码（4 位十进制字符串）
    function_code: int  # 功能码
    function_desc: str  # 功能码描述
    direction: int  # 上下行标志
    direction_desc: str
    message_type: str  # 报文类型（2 字符，如 "A1"）
    message_type_desc: str
    body_length: int  # 报文正文长度

    # ===== 正文信息 =====
    has_time: bool  # 是否带时间
    body_time: datetime | None  # 正文时间（若带）
    elements: list[ElementValue] = field(default_factory=list)

    # ===== 原始数据 =====
    raw_frame: bytes = b""  # 完整原始帧
    header_bytes: bytes = b""  # 帧头字节
    body_bytes: bytes = b""  # 正文字节
    crc_received: int = 0  # 接收到的 CRC
    crc_calculated: int = 0  # 计算得到的 CRC
    crc_ok: bool = True  # CRC 校验是否通过

    def to_dict(self) -> dict:
        """转为字典（便于序列化）。"""
        return {
            "center_station_addr": self.center_station_addr,
            "remote_station_addr": self.remote_station_addr,
            "password": self.password,
            "function_code": f"0x{self.function_code:02X}",
            "function_desc": self.function_desc,
            "direction": self.direction_desc,
            "message_type": self.message_type,
            "message_type_desc": self.message_type_desc,
            "body_length": self.body_length,
            "has_time": self.has_time,
            "body_time": self.body_time.strftime("%Y-%m-%d %H:%M:%S") if self.body_time else None,
            "elements": [
                {
                    "identifier": el.identifier,
                    "name": el.name,
                    "unit": el.unit,
                    "value": el.display_value,
                    "raw_value": el.raw_value,
                    "raw_hex": bytes_to_hex_compact(el.raw_bytes),
                }
                for el in self.elements
            ],
            "crc_ok": self.crc_ok,
            "crc_received": f"0x{self.crc_received:04X}",
            "crc_calculated": f"0x{self.crc_calculated:04X}",
            "raw_frame_hex": bytes_to_hex_compact(self.raw_frame),
        }


class DecodeError(Exception):
    """解码异常。"""


class SL651Decoder:
    """SL651 报文解码器。

    用法::

        decoder = SL651Decoder()
        result = decoder.decode_hex("7E ... 7E")
        print(result.to_dict())
    """

    def decode_hex(self, hex_str: str) -> DecodedMessage:
        """解析十六进制字符串形式的报文。"""
        from .bcd import hex_str_to_bytes

        return self.decode(hex_str_to_bytes(hex_str))

    def decode(self, frame: bytes) -> DecodedMessage:
        """解析 bytes 形式的报文。

        支持两种输入：
        1. 包含起始符和结束符的完整帧：``7E ... 7E``
        2. 不含起止符的裸帧（从中心站地址开始）
        """
        if not frame:
            raise DecodeError("报文为空")

        # 处理起止符
        has_delimiters = frame[0] == C.START_END
        if has_delimiters:
            if frame[-1] != C.START_END:
                raise DecodeError("报文以 0x7E 起始但未以 0x7E 结束")
            if len(frame) < C.HEADER_LEN + 4:  # 起止符2 + CRC2 + 至少1字节正文
                raise DecodeError(f"报文长度不足: {len(frame)} 字节")
            payload = frame[1:-1]  # 去掉起止符
        else:
            if len(frame) < C.HEADER_LEN + 2:  # CRC2 + 至少1字节正文
                raise DecodeError(f"裸帧长度不足: {len(frame)} 字节")
            payload = frame

        # 解析帧头
        header = payload[: C.HEADER_LEN]
        body_with_crc = payload[C.HEADER_LEN :]
        if len(body_with_crc) < 2:
            raise DecodeError("报文正文 + CRC 长度不足")

        # CRC 校验：计算范围 = 帧头 + 报文正文（不含 CRC 自身）
        body = body_with_crc[:-2]
        crc_received = int.from_bytes(body_with_crc[-2:], "big")
        crc_calculated = crc16(header + body)
        crc_ok = crc_received == crc_calculated

        # 解析帧头各字段
        center_addr = f"{bcd_to_int(header[0]):02d}"
        remote_addr = "".join(f"{bcd_to_int(b):02d}" for b in header[1:6])
        password = "".join(f"{bcd_to_int(b):02d}" for b in header[6:8])
        function_code = header[8]
        direction = header[9]
        # 报文类型为 1 字节 BCD，转成 "A1" 形式
        mt_hi = (header[10] >> 4) & 0x0F
        mt_lo = header[10] & 0x0F
        message_type = f"{mt_hi:X}{mt_lo:X}"
        body_length = bcd_bytes_to_int(header[11:13])

        function_desc = C.FUNCTION_CODES.get(function_code, f"未知功能码 0x{function_code:02X}")
        direction_desc = "上行（遥测站→中心站）" if direction == C.DIR_UPSTREAM else "下行（中心站→遥测站）"
        message_type_desc = C.MESSAGE_TYPES.get(message_type, "未知报文类型")

        # 解析正文
        has_time, body_time, elements = self._parse_body(body)

        return DecodedMessage(
            center_station_addr=center_addr,
            remote_station_addr=remote_addr,
            password=password,
            function_code=function_code,
            function_desc=function_desc,
            direction=direction,
            direction_desc=direction_desc,
            message_type=message_type,
            message_type_desc=message_type_desc,
            body_length=body_length,
            has_time=has_time,
            body_time=body_time,
            elements=elements,
            raw_frame=frame,
            header_bytes=header,
            body_bytes=body,
            crc_received=crc_received,
            crc_calculated=crc_calculated,
            crc_ok=crc_ok,
        )

    def _parse_body(self, body: bytes) -> tuple[bool, datetime | None, list[ElementValue]]:
        """解析报文正文。

        返回 (是否带时间, 时间, 要素列表)。
        """
        if not body:
            return False, None, []

        pos = 0
        time_flag = body[pos]
        pos += 1
        has_time = bool(time_flag & C.TIME_FLAG_WITH_TIME)

        body_time: datetime | None = None
        if has_time:
            if len(body) < pos + 6:
                raise DecodeError("报文标记带时间但时间字段不足 6 字节")
            body_time = bcd_to_datetime(body[pos : pos + 6])
            pos += 6

        elements: list[ElementValue] = []
        # 逐个解析要素，直到正文结束
        while pos < len(body):
            if pos + 2 > len(body):
                break
            # 要素标识符 2 字节 BCD -> 4 位十六进制字符串
            id_hi = body[pos]
            id_lo = body[pos + 1]
            identifier = f"{id_hi:02X}{id_lo:02X}"
            pos += 2

            element_def = C.ELEMENT_IDENTIFIERS.get(identifier)
            if element_def is None:
                # 未知要素，按剩余字节全部读取并停止
                raw = body[pos:]
                elements.append(
                    ElementValue(
                        identifier=identifier,
                        name=f"未知要素({identifier})",
                        unit="-",
                        data_type="unknown",
                        decimals=0,
                        raw_value=bytes_to_hex_compact(raw),
                        raw_bytes=raw,
                    )
                )
                break

            name, unit, data_type, decimals, data_len = element_def
            if pos + data_len > len(body):
                raise DecodeError(
                    f"要素 {identifier}({name}) 数据长度 {data_len} 超出剩余正文长度 {len(body) - pos}"
                )
            raw_bytes = body[pos : pos + data_len]
            pos += data_len

            value = self._parse_element_value(data_type, decimals, raw_bytes)
            elements.append(
                ElementValue(
                    identifier=identifier,
                    name=name,
                    unit=unit,
                    data_type=data_type,
                    decimals=decimals,
                    raw_value=value,
                    raw_bytes=raw_bytes,
                )
            )

        return has_time, body_time, elements

    @staticmethod
    def _parse_element_value(data_type: str, decimals: int, raw: bytes) -> Any:
        """根据数据类型解析单个要素的值。"""
        if data_type == "float":
            # BCD 编码，最高字节最高位为 1 表示负数
            negative = bool(raw[0] & 0x80)
            sanitized = bytes([(raw[0] & 0x7F)] + list(raw[1:]))
            int_val = bcd_bytes_to_int(sanitized)
            float_val = int_val / (10 ** decimals) if decimals > 0 else float(int_val)
            return -float_val if negative else float_val

        if data_type == "int":
            negative = bool(raw[0] & 0x80)
            sanitized = bytes([(raw[0] & 0x7F)] + list(raw[1:]))
            int_val = bcd_bytes_to_int(sanitized)
            return -int_val if negative else int_val

        if data_type == "datetime":
            return bcd_to_datetime(raw)

        if data_type == "datetime_range":
            start = bcd_to_datetime(raw[:6])
            end = bcd_to_datetime(raw[6:12])
            return (start, end)

        if data_type == "string":
            # 字符串以 ASCII 字符填充，去除尾部 0x00 / 0xFF
            return raw.rstrip(b"\x00\xff").decode("ascii", errors="replace")

        return bytes_to_hex_compact(raw)


def decode_hex(hex_str: str) -> DecodedMessage:
    """便捷函数：解析十六进制字符串报文。"""
    return SL651Decoder().decode_hex(hex_str)


def decode(frame: bytes) -> DecodedMessage:
    """便捷函数：解析 bytes 报文。"""
    return SL651Decoder().decode(frame)
