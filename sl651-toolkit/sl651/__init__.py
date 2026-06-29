"""SL651-2014 水文监测数据通信规约 工具包。"""

from .bcd import (
    bcd_bytes_to_int,
    bcd_bytes_to_int_le,
    bcd_to_datetime,
    bcd_to_int,
    bcd5_to_datetime,
    bytes_to_hex,
    bytes_to_hex_compact,
    datetime_to_bcd,
    hex_str_to_bytes,
    int_to_bcd,
    int_to_bcd_bytes,
    safe_bcd_to_int,
)
from .constants import (
    FUNC_MAP,
    SL651_CUSTOM,
    SL651_ELEMENTS,
    STATION_TYPE,
    STATUS_0,
    STATUS_1,
    STATUS_BITS,
    parse_def_byte,
)
from .crc import crc8, crc16, crc16_bytes
from .decoder import DecodeError, DecodedMessage, ElementValue, SL651Decoder, decode, decode_hex
from .encoder import EncodeError, SL651Encoder

__all__ = [
    "bcd_to_int", "int_to_bcd", "bcd_bytes_to_int", "bcd_bytes_to_int_le",
    "int_to_bcd_bytes", "bcd_to_datetime", "bcd5_to_datetime",
    "datetime_to_bcd", "hex_str_to_bytes", "bytes_to_hex",
    "bytes_to_hex_compact", "safe_bcd_to_int",
    "FUNC_MAP", "STATION_TYPE", "SL651_ELEMENTS", "SL651_CUSTOM",
    "STATUS_BITS", "STATUS_0", "STATUS_1", "parse_def_byte",
    "crc16", "crc16_bytes", "crc8",
    "SL651Decoder", "DecodedMessage", "ElementValue", "DecodeError",
    "decode", "decode_hex",
    "SL651Encoder", "EncodeError",
]

__version__ = "1.1.0"
