"""SL651 / SLT427 协议 BCD 编解码与字节流工具。"""

from __future__ import annotations

from datetime import datetime


def bcd_to_int(bcd: int) -> int:
    """单字节 BCD -> 整数。0x59 -> 59。"""
    hi = (bcd >> 4) & 0x0F
    lo = bcd & 0x0F
    if hi > 9 or lo > 9:
        raise ValueError(f"无效 BCD 字节: 0x{bcd:02X}")
    return hi * 10 + lo


def int_to_bcd(value: int) -> int:
    """整数 -> 单字节 BCD。59 -> 0x59。"""
    if not 0 <= value <= 99:
        raise ValueError(f"BCD 数值超出范围 (0-99): {value}")
    return ((value // 10) << 4) | (value % 10)


def bcd_bytes_to_int(data: bytes) -> int:
    """多字节 BCD（大端） -> 整数。"""
    result = 0
    for byte in data:
        result = result * 100 + bcd_to_int(byte)
    return result


def bcd_bytes_to_int_le(data: bytes) -> int:
    """多字节 BCD（小端） -> 整数。用于 SLT427 数据域。"""
    result = 0
    for i in range(len(data) - 1, -1, -1):
        result = result * 100 + bcd_to_int(data[i])
    return result


def int_to_bcd_bytes(value: int, length: int) -> bytes:
    """整数 -> 指定长度 BCD 字节序列（大端）。超限抛 ValueError。"""
    if length <= 0:
        return b""
    max_val = 10 ** (length * 2) - 1
    if value < 0 or value > max_val:
        raise ValueError(f"值 {value} 超出 {length} 字节 BCD 范围 (0~{max_val})")
    digits = f"{value:0{length * 2}d}"
    return bytes(int_to_bcd(int(digits[i: i + 2])) for i in range(0, len(digits), 2))


def bcd_to_datetime(data: bytes) -> datetime:
    """6 字节 BCD 时间 -> datetime。YY MM DD HH mm SS。"""
    if len(data) != 6:
        raise ValueError(f"时间字段长度必须为 6 字节，实际 {len(data)}")
    year = 2000 + bcd_to_int(data[0])
    month = bcd_to_int(data[1])
    day = bcd_to_int(data[2])
    hour = bcd_to_int(data[3])
    minute = bcd_to_int(data[4])
    second = bcd_to_int(data[5])
    return datetime(year, month, day, hour, minute, second)


def bcd5_to_datetime(data: bytes) -> datetime:
    """5 字节 BCD 时间 -> datetime。YY MM DD HH mm（无秒）。"""
    if len(data) != 5:
        raise ValueError(f"时间字段长度必须为 5 字节，实际 {len(data)}")
    year = 2000 + bcd_to_int(data[0])
    month = bcd_to_int(data[1])
    day = bcd_to_int(data[2])
    hour = bcd_to_int(data[3])
    minute = bcd_to_int(data[4])
    return datetime(year, month, day, hour, minute, 0)


def datetime_to_bcd(dt: datetime) -> bytes:
    """datetime -> 6 字节 BCD。"""
    return bytes([
        int_to_bcd(dt.year - 2000),
        int_to_bcd(dt.month),
        int_to_bcd(dt.day),
        int_to_bcd(dt.hour),
        int_to_bcd(dt.minute),
        int_to_bcd(dt.second),
    ])


def hex_str_to_bytes(hex_str: str) -> bytes:
    """十六进制字符串 -> bytes。"""
    cleaned = "".join(hex_str.split())
    if len(cleaned) % 2 != 0:
        raise ValueError("十六进制字符串长度必须为偶数")
    return bytes.fromhex(cleaned)


def bytes_to_hex(data: bytes, sep: str = " ") -> str:
    """bytes -> 带分隔符的十六进制字符串。"""
    return sep.join(f"{b:02X}" for b in data)


def bytes_to_hex_compact(data: bytes) -> str:
    """bytes -> 紧凑十六进制字符串。"""
    return data.hex().upper()


def safe_bcd_to_int(b: int) -> int | None:
    """安全 BCD 解码，遇到无效值返回 None。"""
    hi = (b >> 4) & 0x0F
    lo = b & 0x0F
    if hi > 9 or lo > 9:
        return None
    return hi * 10 + lo
