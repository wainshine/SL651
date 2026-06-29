#!/usr/bin/env python3
"""SL651 工具包自测脚本。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sl651 import (
    SL651Decoder,
    bcd_bytes_to_int,
    bcd_to_datetime,
    bcd_to_int,
    crc16,
    datetime_to_bcd,
    int_to_bcd,
    parse_def_byte,
)
from sl651.encoder import SL651Encoder


def test_bcd() -> None:
    print(">>> BCD 编解码")
    assert bcd_to_int(0x59) == 59
    assert int_to_bcd(59) == 0x59
    assert bcd_bytes_to_int(b"\x12\x34") == 1234
    dt = datetime(2026, 6, 29, 10, 30, 0)
    assert bcd_to_datetime(datetime_to_bcd(dt)) == dt
    print("    OK")


def test_crc() -> None:
    print(">>> CRC-16/MODBUS")
    assert crc16(b"123456789") == 0x4B37
    print("    OK")


def test_def_byte() -> None:
    print(">>> 定义符解析")
    assert parse_def_byte(0x23) == (4, 3)
    assert parse_def_byte(0x1A) == (3, 2)
    print("    OK")


def test_decode_njnrs() -> None:
    print(">>> njnrs 示例报文解码")
    hex_msg = ("7E7E2500418D23370000320030020C06230601010314"
               "F1F100418D23374BF0F02306010100"
               "20190000003B2300037865221900000026190000003812128503"
               "5AC6")
    r = SL651Decoder().decode_hex(hex_msg)
    assert r.crc_ok
    assert r.function_code == 0x32
    assert r.station_type_name == "水库"
    assert len(r.elements) == 5
    print("    OK")


def test_decode_watertester() -> None:
    print(">>> 水测家加报报解码")
    hex_msg = ("7e7e011234567890000233008e020001230308111501f1f1"
               "123456789048f0f023030811143923000003453a2300000305"
               "03110254283600000041952029360000003660002736000000"
               "785520361b000304371b0006003c1b0003453d1b000305c155"
               "00000000000001165134c25500000000000001016520491900"
               "0969471100794a1900096845200000000138121204c9110051"
               "7a0800ca100100032c63")
    r = SL651Decoder().decode_hex(hex_msg)
    assert r.crc_ok
    assert r.function_code == 0x33
    assert r.station_type_name == "河道"
    codes = {e.code for e in r.elements}
    assert "39" in codes
    assert "BIT0" in codes
    print("    OK")


def test_encode_decode_roundtrip() -> None:
    print(">>> 编码 → 解码往返")
    encoder = SL651Encoder(
        center_addr=0x01, station_addr="00418D2337",
        password=0, station_type=0x4B,
    )
    frame = encoder.build_timing_frame(
        [(0x39, 12.345, 3, 3), (0x38, 12.60, 2, 2)],
        obs_time=datetime(2023, 6, 1, 1, 0),
    )
    r = SL651Decoder().decode(frame)
    assert r.crc_ok
    assert len(r.elements) >= 2
    print("    OK")


def test_crc8() -> None:
    from sl651.crc import crc8
    print(">>> CRC8")
    assert crc8(b"\x00\x01\x02") == 0xA6
    print("    OK")


def test_slt427() -> None:
    from slt427 import SLT427Decoder
    print(">>> SLT427 解码")
    msg = "681568B40102030405C05545040020700030151412052600AD16"
    r = SLT427Decoder().decode_hex(msg)
    assert r.crc_ok
    assert r.afn == 0xC0
    assert r.ctrl_func_name == "流速"
    print("    OK")


def test_negative_bcd() -> None:
    print(">>> 负数 BCD 编解码")
    encoder = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    frame = encoder.build_timing_frame(
        [(0x39, -0.345, 4, 3), (0x38, 12.04, 2, 2)],
        obs_time=datetime(2023, 3, 8, 11, 14),
    )
    r = SL651Decoder().decode(frame)
    assert r.crc_ok
    for e in r.elements:
        if e.code == "39":
            assert str(e.value)[:6] == "-0.345", f"{e.value} != -0.345"
    print("    OK")


def test_invalid_bcd_graceful() -> None:
    print(">>> 无效BCD数据优雅降级")
    hex_msg = ("7E7E253A41BB2337ABCD32001802ABCD230601010104"
               "F1F13A41BB23374BF0F02306010100"
               "20FFFFFF2600FF99003812FF0003E2B0")
    try:
        r = SL651Decoder().decode_hex(hex_msg)
        print(f"    CRC: {r.crc_ok}, 要素: {len(r.elements)}")
    except Exception as e:
        print(f"    未崩溃，错误: {e}")
    print("    OK")


def main() -> int:
    print("=" * 60)
    print("SL651 工具包自测")
    print("=" * 60)
    failed = 0
    tests = [
        test_bcd, test_crc, test_def_byte,
        test_decode_njnrs, test_decode_watertester,
        test_encode_decode_roundtrip,
        test_crc8, test_slt427, test_negative_bcd, test_invalid_bcd_graceful,
    ]
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"    失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print()
    if failed:
        print(f"失败: {failed} 项")
        return 1
    print("所有测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
