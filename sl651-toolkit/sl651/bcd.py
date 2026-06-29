"""SL651 协议 BCD 编解码与字节流工具。"""

from __future__ import annotations

from datetime import datetime


def bcd_to_int(bcd: int) -> int:
    """将单字节 BCD 编码转为整数。例如 0x59 -> 59。"""
    hi = (bcd >> 4) & 0x0F
    lo = bcd & 0x0F
    if hi > 9 or lo > 9:
        raise ValueError(f"无效的 BCD 字节: 0x{bcd:02X}")
    return hi * 10 + lo


def int_to_bcd(value: int) -> int:
    """将整数转为单字节 BCD。例如 59 -> 0x59。"""
    if not 0 <= value <= 99:
        raise ValueError(f"BCD 编码数值超出范围 (0-99): {value}")
    return ((value // 10) << 4) | (value % 10)


def bcd_bytes_to_int(data: bytes) -> int:
    """多字节 BCD 转整数。例如 b'\\x12\\x34' -> 1234。"""
    result = 0
    for byte in data:
        result = result * 100 + bcd_to_int(byte)
    return result


def int_to_bcd_bytes(value: int, length: int) -> bytes:
    """将整数编码为指定长度的 BCD 字节序列。"""
    if length <= 0:
        return b""
    digits = f"{value:0{length * 2}d}"
    return bytes(int_to_bcd(int(digits[i : i + 2])) for i in range(0, len(digits), 2))


def bcd_to_datetime(data: bytes) -> datetime:
    """6 字节 BCD 时间 -> datetime（年月日时分秒）。

    SL651 时间格式：YY MM DD HH mm ss（每字节 BCD）。
    年份使用 2 位，按 2000 + YY 处理。
    """
    if len(data) != 6:
        raise ValueError(f"时间字段长度必须为 6 字节，实际 {len(data)}")
    year = 2000 + bcd_to_int(data[0])
    month = bcd_to_int(data[1])
    day = bcd_to_int(data[2])
    hour = bcd_to_int(data[3])
    minute = bcd_to_int(data[4])
    second = bcd_to_int(data[5])
    return datetime(year, month, day, hour, minute, second)


def datetime_to_bcd(dt: datetime) -> bytes:
    """datetime -> 6 字节 BCD 时间。"""
    return bytes(
        [
            int_to_bcd(dt.year - 2000),
            int_to_bcd(dt.month),
            int_to_bcd(dt.day),
            int_to_bcd(dt.hour),
            int_to_bcd(dt.minute),
            int_to_bcd(dt.second),
        ]
    )


def hex_str_to_bytes(hex_str: str) -> bytes:
    """将十六进制字符串（可含空格/换行）转为 bytes。"""
    cleaned = "".join(hex_str.split())
    if len(cleaned) % 2 != 0:
        raise ValueError("十六进制字符串长度必须为偶数")
    return bytes.fromhex(cleaned)


def bytes_to_hex(data: bytes, sep: str = " ") -> str:
    """bytes -> 十六进制字符串。"""
    return sep.join(f"{b:02X}" for b in data)


def bytes_to_hex_compact(data: bytes) -> str:
    """bytes -> 紧凑十六进制字符串（无分隔符）。"""
    return data.hex().upper()
