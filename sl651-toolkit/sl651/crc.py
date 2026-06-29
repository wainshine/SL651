"""SL651 协议 CRC-16/CCITT 校验。

SL651-2014 规约规定使用 CRC-16/CCITT (多项式 0x1021, 初始值 0xFFFF)，
计算范围从「中心站地址」开始到「报文正文」结束（不含起始符 0x7E、
不含 CRC 自身、不含结束符 0x7E）。
"""

from __future__ import annotations

# 预生成 CRC-16/CCITT 查找表，提升批量解码性能
_POLY = 0x1021
_CRC_TABLE: list[int] = []


def _build_table() -> None:
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        _CRC_TABLE.append(crc)


_build_table()


def crc16(data: bytes) -> int:
    """计算给定字节序列的 CRC-16/CCITT 校验值。"""
    crc = 0xFFFF
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC_TABLE[((crc >> 8) ^ byte) & 0xFF]
    return crc & 0xFFFF


def crc16_bytes(data: bytes) -> bytes:
    """返回 CRC 校验值的 2 字节大端表示。"""
    return crc16(data).to_bytes(2, "big")


def verify(data: bytes, expected: bytes) -> bool:
    """校验 data 的 CRC 是否与 expected (2 字节) 一致。"""
    return crc16_bytes(data) == expected
