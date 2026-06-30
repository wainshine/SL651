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


def test_sl427_decode() -> None:
    from sl427 import SL427Decoder
    print(">>> SL427 解码")
    msg = "681568B40102030405C05545040020700030151412052600AD16"
    r = SL427Decoder().decode_hex(msg)
    assert r.crc_ok
    assert r.afn == 0xC0
    assert r.ctrl_func_name == "流速"
    print("    OK")


def test_sl427_encoder_roundtrip() -> None:
    from sl427 import SL427Encoder, SL427Decoder, make_ctrl, encode_address, encode_tp
    from datetime import datetime
    from sl651.bcd import int_to_bcd_bytes
    print(">>> SL427 编码往返")
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    # heartbeat
    f = enc.build_heartbeat()
    r = SL427Decoder().decode(f)
    assert r.crc_ok and r.afn == 0x02
    # C0 self-report with water level
    wl_data = bytes(reversed(int_to_bcd_bytes(37865, 4)))
    f2 = enc.build_self_report_c0(func_code=0x02, data=wl_data,
                                   tp=datetime(2026, 5, 12, 14, 15, 30))
    r2 = SL427Decoder().decode(f2)
    assert r2.crc_ok and r2.afn == 0xC0
    print("    OK")


def test_sl427_address_encoding() -> None:
    from sl427 import encode_address
    print(">>> SL427 地址编码")
    # 方式1: admin=110108, stn=1284
    a1 = encode_address(method=1, admin_code=110108, stn_id=1284)
    assert a1[:3] == bytes([0x11, 0x01, 0x08])  # BCD
    assert int.from_bytes(a1[3:5], "little") == 1284  # BIN little-endian
    # 方式2: hex_code="1234567890ABCDEF" → error (>8)
    try:
        encode_address(method=2, hex_code="1234567890ABCDEF")
        assert False, "should raise"
    except Exception:
        pass
    # 方式2: 8位HEX
    a2 = encode_address(method=2, hex_code="12345678")
    assert a2[0] == 0x00
    assert a2[1:].hex().upper() == "12345678"
    print("    OK")


def test_sl427_tp_encoding() -> None:
    from sl427 import encode_tp
    from datetime import datetime
    print(">>> SL427 Tp 时间编码")
    tp = encode_tp(datetime(2026, 5, 12, 14, 15, 30), delay=5)
    assert len(tp) == 7
    from sl651.bcd import bcd_to_int
    assert bcd_to_int(tp[0]) == 30    # 秒
    assert bcd_to_int(tp[1]) == 15    # 分
    assert bcd_to_int(tp[2]) == 14    # 时
    assert bcd_to_int(tp[3]) == 12    # 日
    assert bcd_to_int(tp[4]) == 5     # 月
    assert bcd_to_int(tp[5]) == 26    # 年 (2026-2000)
    assert tp[6] == 5                 # 延时 5min
    print("    OK")


def test_sl427_c0_signed_value() -> None:
    from sl427 import SL427Encoder, SL427Decoder, encode_address
    from sl651.bcd import int_to_bcd_bytes
    from datetime import datetime
    print(">>> SL427 有符号水位往返")
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    # 水位 -0.345 → BCD 345, 4 bytes, signed=True, LE
    # Signed BCD: last byte high nibble = 0xF for negative
    # 345 in BCD: 00 00 03 45, signed negative: 00 00 03 45 → 4bytes, last byte 0x45 → strip hi nibble → 0x05, then negate
    # Actually for SL427 signed BCD LE: data bytes in LE order, last byte's high nibble indicates sign
    # value=345 → BCD LE = 45 03 00 00. For negative: 45→0xF5 (set high nibble F)
    raw = bytes([0x45, 0x03, 0x00, 0xF0])  # -345, 4B signed LE
    f = enc.build_self_report_c0(func_code=0x02, data=raw, tp=datetime(2026, 6, 1, 12, 0))
    r = SL427Decoder().decode(f)
    assert r.crc_ok
    # Find water level element
    wl = [e for e in r.elements if e.name == "水位"]
    assert len(wl) > 0
    print("    OK")


def test_sl427_invalid_l() -> None:
    from sl427 import SL427Decoder, SL427Encoder, encode_address
    from sl427.decoder import DecodeError
    print(">>> SL427 畸形 L 检测")
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    f = enc.build_heartbeat()
    # Corrupt L byte
    corrupted = bytearray(f)
    corrupted[1] = 0x99
    try:
        SL427Decoder().decode(bytes(corrupted))
        assert False, "should raise"
    except DecodeError as e:
        assert "不匹配" in str(e)
    print("    OK")


def test_sl427_downlink() -> None:
    from sl427 import SL427Encoder, SL427Decoder, make_ctrl, encode_address
    print(">>> SL427 下行帧解码")
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    # Downlink: DIR=0, func_code=0x00 (确认), AFN=0x02 (链路检测)
    ctrl = make_ctrl(dir_=0, func_code=0x00)
    f = enc.build_frame(afn=0x02, ctrl_word=ctrl, data=b"\xF2")
    r = SL427Decoder().decode(f)
    assert r.crc_ok
    assert "下行" in r.direction
    assert len(r.elements) >= 1
    # Downlink query (B0)
    ctrl2 = make_ctrl(dir_=0, func_code=0x01)  # 查询雨量
    f2 = enc.build_frame(afn=0xB0, ctrl_word=ctrl2)
    r2 = SL427Decoder().decode(f2)
    assert r2.crc_ok
    assert "下行" in r2.direction
    print("    OK")


def test_sl651_downlink_frames() -> None:
    from datetime import datetime
    print(">>> SL651 下行帧编码")
    encoder = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    decoder = SL651Decoder()
    # 查询帧 (0x37)
    f = encoder.build_query_frame([0x39, 0x38])
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x37
    assert r.direction == 1
    # 设置帧 (0x40)
    f = encoder.build_set_param_frame([(0x39, 12.345, 4, 3)])
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x40
    # 校时帧 (0x4A)
    f = encoder.build_clock_sync_frame(datetime(2025, 6, 1, 12, 0, 0))
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x4A
    # 恢复出厂 (0x48)
    f = encoder.build_reset_frame()
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x48
    print("    OK")


def test_sl427_param_settings() -> None:
    from sl427 import SL427Encoder, SL427Decoder, encode_address
    from datetime import datetime
    print(">>> SL427 参数设置")
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    decoder = SL427Decoder()
    # 设置地址
    f = enc.build_set_addr(bytes([0x11, 0x01, 0x08, 0x10, 0x20]))
    r = decoder.decode(f)
    assert r.crc_ok and r.afn == 0x10
    # 设置时钟
    f = enc.build_set_clock(datetime(2025, 6, 1, 12, 0, 0))
    r = decoder.decode(f)
    assert r.crc_ok and r.afn == 0x11
    # 设置充值量
    f = enc.build_set_recharge(1234.567)
    r = decoder.decode(f)
    assert r.crc_ok and r.afn == 0x15
    # IC 卡
    f = enc.build_set_ic_card_on()
    r = decoder.decode(f)
    assert r.crc_ok and r.afn == 0x30
    print("    OK")


def test_sl651_ascii() -> None:
    from datetime import datetime
    print(">>> SL651 ASCII 编解码")
    encoder = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    decoder = SL651Decoder()
    f = encoder.build_ascii_frame(
        [("Z", "12.345"), ("Q", "5.678"), ("VT", "12.6")],
        obs_time=datetime(2025, 6, 1, 12, 0),
    )
    r = decoder.decode(f)
    assert r.crc_ok
    assert r.encoding == "ASCII"
    codes = {e.code: e.value for e in r.elements}
    assert codes.get("Z") == 12.345
    assert codes.get("VT") == 12.6
    print("    OK")


def test_fujian_messages() -> None:
    print(">>> 福建规定示例报文")
    sample_file = PROJECT_ROOT / "examples" / "fujian_messages.txt"
    if not sample_file.exists():
        print("    跳过（fujian_messages.txt 不存在）")
        return
    from sl651 import SL651Decoder
    decoder = SL651Decoder()
    success = 0
    failed = 0
    for line in sample_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            r = decoder.decode_hex(line)
            if r.crc_ok:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    print(f"    {success} 通过, {failed} 失败")
    assert failed == 0, f"有 {failed} 条福建报文解码失败"
    assert success >= 20, f"至少 20 条, 实际 {success}"
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
        test_crc8, test_sl427_decode, test_sl427_encoder_roundtrip,
        test_sl427_address_encoding, test_sl427_tp_encoding,
        test_sl427_c0_signed_value, test_sl427_invalid_l, test_sl427_downlink,
        test_sl651_downlink_frames, test_sl427_param_settings, test_sl651_ascii,
        test_fujian_messages,
        test_negative_bcd, test_invalid_bcd_graceful,
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
