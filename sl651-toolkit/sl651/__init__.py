"""SL651-2014 水文监测数据通信规约 工具包。

提供报文解码、编码能力，供水文/雨量/墒情等遥测站数据处理使用。
"""

from .bcd import (
    bcd_bytes_to_int,
    bcd_to_datetime,
    bcd_to_int,
    bytes_to_hex,
    bytes_to_hex_compact,
    datetime_to_bcd,
    hex_str_to_bytes,
    int_to_bcd,
    int_to_bcd_bytes,
)
from .constants import (
    DEVICE_TYPES,
    ELEMENT_IDENTIFIERS,
    FUNCTION_CODES,
    MESSAGE_TYPES,
    START_END,
)
from .crc import crc16, crc16_bytes, verify
from .decoder import DecodeError, DecodedMessage, ElementValue, SL651Decoder, decode, decode_hex
from .encoder import EncodeError, SL651Encoder

__all__ = [
    # BCD 工具
    "bcd_to_int",
    "int_to_bcd",
    "bcd_bytes_to_int",
    "int_to_bcd_bytes",
    "bcd_to_datetime",
    "datetime_to_bcd",
    "hex_str_to_bytes",
    "bytes_to_hex",
    "bytes_to_hex_compact",
    # 常量
    "START_END",
    "FUNCTION_CODES",
    "MESSAGE_TYPES",
    "ELEMENT_IDENTIFIERS",
    "DEVICE_TYPES",
    # CRC
    "crc16",
    "crc16_bytes",
    "verify",
    # 解码器
    "SL651Decoder",
    "DecodedMessage",
    "ElementValue",
    "DecodeError",
    "decode",
    "decode_hex",
    # 编码器
    "SL651Encoder",
    "EncodeError",
]

__version__ = "1.0.0"
