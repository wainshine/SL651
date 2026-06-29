"""SL651 / SLT427 协议校验算法。

- CRC-16/MODBUS: SL651, 多项式 0xA001 (0x8005 反转), 初值 0xFFFF
- CRC8: SLT427, 多项式 0xE5, 初值 0x00
"""

from __future__ import annotations

_POLY_CRC8 = 0xE5


def crc16(data: bytes) -> int:
    """计算 SL651 CRC-16/MODBUS 校验值。

    多项式 0xA001 (0x8005 反转)，初值 0xFFFF。
    验证: crc16(b'123456789') == 0x4B37
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc16_bytes(data: bytes) -> bytes:
    """返回 CRC16 校验值的 2 字节大端表示。"""
    return crc16(data).to_bytes(2, "big")


def crc8(data: bytes) -> int:
    """计算 SLT427 CRC8 校验值（多项式 0xE5，初值 0x00）。"""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ _POLY_CRC8) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc & 0xFF
