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
    from sl651.constants import ENQ
    print(">>> SL651 下行帧编码")
    encoder = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    decoder = SL651Decoder()
    # 查询帧 (0x37, 表42: 仅流水号+发报时间=8B, 结束符 ENQ)
    f = encoder.build_query_frame()
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x37
    assert r.direction == 1
    assert r.body_length == 8, f"查询帧正文应为8字节, 实际{r.body_length}"
    # 验证结束符为 ENQ
    end_byte = list(f)[-3]  # CRC前1字节
    assert end_byte == ENQ, f"查询帧结束符应为ENQ(05H)，实际 {end_byte:02X}H"
    # 设置帧 (0x40)
    f = encoder.build_set_param_frame([(0x39, 12.345, 4, 3)])
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x40
    # 校时帧 (0x4A, 表67: 发报时间即校时值)
    sync_dt = datetime(2025, 6, 1, 12, 0, 0)
    f = encoder.build_clock_sync_frame(sync_dt)
    r = decoder.decode(f)
    assert r.crc_ok and r.function_code == 0x4A
    assert r.body_length == 8, f"校时帧正文应为8字节, 实际{r.body_length}"
    # 上行帧结束符应为 ETX
    # 上行帧结束符应为 ETX
    f_up = encoder.build_timing_frame([(0x39, 12.345, 4, 3)])
    assert list(f_up)[-3] == 0x03, f"上行帧结束符应为ETX(03H)"
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
    print(">>> SL651 新 ASCII 编解码")
    encoder = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    decoder = SL651Decoder()
    f = encoder.build_ascii_frame(
        [("Z", "12.345"), ("Q", "5.678"), ("VT", "12.6")],
        obs_time=datetime(2025, 6, 1, 12, 0),
    )
    r = decoder.decode(f)
    assert r.crc_ok, f"CRC 失败: calc={r.crc_calculated:04X} recv={r.crc_received:04X}"
    assert r.encoding == "ASCII", f"编码类型应为 ASCII，实际 {r.encoding}"
    codes = {e.code: e.value for e in r.elements}
    assert codes.get("Z") == 12.345, f"Z = {codes.get('Z')}"
    assert codes.get("VT") == 12.6, f"VT = {codes.get('VT')}"
    assert codes.get("Q") == 5.678, f"Q = {codes.get('Q')}"
    print("    OK")


def test_sl651_ascii_roundtrip() -> None:
    from datetime import datetime
    print(">>> SL651 新 ASCII 往返测试")
    encoder = SL651Encoder(center_addr=0x37, station_addr="1234567890", password=0xABCD, station_type=0x48)
    decoder = SL651Decoder()
    f = encoder.build_ascii_frame(
        [("Z", "12.345"), ("Q", "5.678"), ("VT", "12.6")],
        obs_time=datetime(2025, 6, 1, 12, 0),
    )
    r = decoder.decode(f)
    assert r.crc_ok
    assert r.encoding == "ASCII"
    assert r.center_addr == "37"
    assert r.station_addr == "1234567890"
    assert r.password == "ABCD"
    assert r.function_code == 0x32
    assert r.direction == 0
    assert r.station_type_name == "河道"
    assert len(r.elements) == 3
    codes = {e.code: e.value for e in r.elements}
    assert codes.get("Z") == 12.345
    assert codes.get("Q") == 5.678
    assert codes.get("VT") == 12.6
    print("    OK")


# 真实报文要素级基线：(功能码, 要素总数, 首要素码, 首值, 末要素码, 末值)
# 首/末值 None 表示跳过数值断言（如 F3 图片为动态摘要字符串）。
# 该基线用于防止「CRC 通过但要素解析错误」的静默回归（审计 v2.2 M-4）。
FUJIAN_BASELINE = [
    (0x49, 0, None, None, None, None),
    (0x34, 14, "F5", "27.30", "38", 12.9),
    (0x32, 3, "20", 5.5, "38", 12.9),
    (0x31, 13, "04", 5, "39", 28.96),
    (0x32, 4, "20", 0.0, "38", 13.12),
    (0x33, 4, "39", 28.96, "38", 13.17),
    (0x34, 28, "F4", "0.0", "38", 13.16),
    (0x35, 0, None, None, None, None),
    (0x36, 2, "F3", None, "05", 7),
    (0x37, 4, "20", 0.0, "38", 11.43),
    (0x38, 13, "04", 0, "F4", "-"),
    (0x3A, 1, "26", 0.0, "26", 0.0),
    (0x41, 0, None, None, None, None),
    (0x43, 0, None, None, None, None),
    (0x45, 1, "56", "-", "56", "-"),
    (0x46, 0, None, None, None, None),
    (0x40, 0, None, None, None, None),
    (0x42, 0, None, None, None, None),
    (0x47, 0, None, None, None, None),
    (0x48, 0, None, None, None, None),
    (0x4A, 0, None, None, None, None),
    (0x51, 0, None, None, None, None),
    (0x50, 0, None, None, None, None),
]

BEIJING_BASELINE = [
    (0x32, 16, "26", 311.3, "FF33", 20.5),
    (0x32, 16, "26", 311.3, "FF33", 20.3),
    (0x32, 14, "26", 1222.2, "38", 14.16),
    (0x32, 14, "26", 1222.2, "38", 12.69),
    (0x33, 13, "22", 0.0, "38", 12.0),
    (0x33, 13, "22", 0.0, "38", 11.98),
    (0x33, 13, "22", 0.0, "38", 11.97),
    (0x32, 13, "22", 0.0, "38", 11.94),
    (0x32, 13, "22", 0.0, "38", 11.9),
    (0x33, 13, "22", 0.0, "38", 11.99),
    (0x32, 13, "22", 0.0, "38", 11.87),
    (0x32, 13, "22", 0.0, "38", 11.81),
    (0x33, 13, "22", 0.0, "38", 11.8),
    (0x34, 14, "F5", "0.00", "38", 12.07),
    (0x34, 14, "F5", "0.00", "38", 12.05),
    (0x34, 27, "F4", "0.0", "38", 13.7),
    (0x34, 27, "F4", "0.0", "38", 13.5),
    (0x32, 5, "39", 33.66, "38", 12.3),
    (0x32, 5, "39", 33.7, "38", 12.3),
    (0x32, 2, "39", 0.0, "38", 12.33),
    (0x34, 14, "F5", "0.00", "38", 12.32),
    (0x34, 14, "F5", "1.07", "38", 12.0),
    (0x34, 14, "F5", "1.09", "38", 12.0),
    (0x32, 2, "26", 184.8, "38", 12.0),
    (0x32, 2, "26", 184.8, "38", 12.0),
]


def _value_eq(actual, expected) -> bool:
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(actual - expected) < 1e-9
    return actual == expected


def _check_baseline(name: str, sample_file: Path, baseline: list) -> None:
    if not sample_file.exists():
        print(f"    跳过（{sample_file.name} 不存在）")
        return
    from sl651 import SL651Decoder
    decoder = SL651Decoder()
    lines = [
        ln.strip() for ln in sample_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert len(lines) == len(baseline), \
        f"{name} 报文数 {len(lines)} != 基线 {len(baseline)}"
    failed = 0
    for i, (line, exp) in enumerate(zip(lines, baseline)):
        func, nelem, fcode, fval, lcode, lval = exp
        r = decoder.decode_hex(line)
        errs = []
        if not r.crc_ok:
            errs.append("CRC 失败")
        if r.function_code != func:
            errs.append(f"功能码 0x{r.function_code:02X} != 0x{func:02X}")
        if len(r.elements) != nelem:
            errs.append(f"要素数 {len(r.elements)} != {nelem}")
        if nelem > 0:
            first, last = r.elements[0], r.elements[-1]
            if first.code != fcode:
                errs.append(f"首要素 {first.code} != {fcode}")
            if fval is not None and not _value_eq(first.value, fval):
                errs.append(f"首值 {first.value!r} != {fval!r}")
            if last.code != lcode:
                errs.append(f"末要素 {last.code} != {lcode}")
            if lval is not None and not _value_eq(last.value, lval):
                errs.append(f"末值 {last.value!r} != {lval!r}")
        if errs:
            failed += 1
            print(f"    [第{i}条] {'; '.join(errs)}")
    assert failed == 0, f"{name} 有 {failed} 条要素级断言失败"
    print(f"    {len(lines)} 条要素级基线全部通过")


def test_fujian_messages() -> None:
    print(">>> 福建规定示例报文（CRC + 要素级基线）")
    _check_baseline("福建", PROJECT_ROOT / "examples" / "fujian_messages.txt",
                    FUJIAN_BASELINE)
    print("    OK")


def test_beijing_messages() -> None:
    print(">>> 北京水务报文验证（CRC + 要素级基线）")
    _check_baseline("北京", PROJECT_ROOT / "examples" / "beijing_messages.txt",
                    BEIJING_BASELINE)
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
    """无效 BCD 降级为 '-'（构造 CRC 正确的帧，避免弱断言）"""
    print(">>> 无效BCD数据优雅降级")
    enc = SL651Encoder(center_addr=1, station_addr="00418D2337",
                       password=0, station_type=0x48)
    frame = bytearray(enc.build_timing_frame(
        [(0x39, 12.345, 4, 3)], obs_time=datetime(2023, 3, 8, 11, 14)))
    # 定位要素数据区并写入非法 BCD 半字节，再重算 CRC 使 CRC 通过
    body_len = ((frame[11] & 0x0F) << 8) | frame[12]
    etx = 14 + body_len
    frame[39] = 0xAB  # 水位数据首字节高半字节 A 非法
    crc = crc16(bytes(frame[:etx + 1]))
    frame[etx + 1] = (crc >> 8) & 0xFF
    frame[etx + 2] = crc & 0xFF

    r = SL651Decoder().decode(bytes(frame))
    assert r.crc_ok, "重算 CRC 后应通过"
    wl = [e for e in r.elements if e.code == "39"]
    assert wl, "应解析出水位要素"
    assert wl[0].value == "-", f"非法 BCD 应降级为 '-', 实际 {wl[0].value!r}"
    print(f"    CRC: {r.crc_ok}, 水位值: {wl[0].value!r} OK")


def test_simulator_engine_smoke() -> None:
    print(">>> 模拟器引擎冒烟测试")
    from simulator import WaterLevelStation, MqttxSender
    from simulator.engine import SimulatorEngine
    from sl651 import SL651Decoder
    sender = MqttxSender(host="127.0.0.1", port=1883)
    engine = SimulatorEngine(sender)
    ws = WaterLevelStation("1234567890")
    engine.add_station(ws)
    # 不启动循环，仅验证 add_station 不崩溃
    assert len(engine.runners) == 1
    # 生成一帧
    enc = engine.runners[0].encoder
    frame = enc.build_timing_frame(ws.generate_elements())
    r = SL651Decoder().decode(frame)
    assert r.crc_ok
    assert r.function_code == 0x32
    print("    OK")


def test_hourly_frame_validation() -> None:
    """M-1: 小时报非 12 组应报错"""
    print(">>> 小时报组数校验")
    from sl651.encoder import EncodeError, SL651Encoder
    enc = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0)
    try:
        enc.build_hourly_frame([0.0] * 5, 12.0, 12.6)
        assert False, "应抛出 EncodeError"
    except EncodeError as e:
        assert "12 组" in str(e)
    # 12 组正常
    f = enc.build_hourly_frame([0.0] * 12, 12.345, 12.6)
    from sl651 import SL651Decoder
    r = SL651Decoder().decode(f)
    assert r.crc_ok
    assert len(r.elements) == 14  # 12 F5 + 1 39 + 1 38
    print("    OK")


def test_recharge_le_bcd() -> None:
    """M-2: 充值量小端 BCD"""
    print(">>> 充值量 LE BCD")
    from sl427 import SL427Encoder, encode_address
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    f = enc.build_set_recharge(1234)
    # 帧: 68 L 68 C(1) A(5) AFN(1) D(4) PW(2) Tp(7) CS(1) 16
    # D 起始 = 1+1+1+1+5+1 = 10
    data = bytes(f)[10:14]
    assert data == bytes([0x34, 0x12, 0x00, 0x00]), \
        f"充值量 LE BCD 应为 34120000，实际 {data.hex().upper()}"
    print("    OK")


# ---------- v1.2.5 审计修复回归测试 ----------

def test_sl651_truncated_uplink() -> None:
    """v1.2.5 H1: 截断上行帧抛 DecodeError 而非 IndexError"""
    from sl651.decoder import DecodeError
    print(">>> SL651 截断上行帧")
    # 18 字节、body_len=0 的畸形上行帧
    f = (bytes.fromhex("7E7E") + bytes([0x25]) + bytes.fromhex("00418D2337")
         + bytes(2) + bytes([0x32]) + bytes([0x80, 0x00]) + bytes([0x02])
         + bytes([0x03]) + bytes(2))
    try:
        SL651Decoder().decode(f)
    except DecodeError:
        pass
    except IndexError:
        raise AssertionError("抛了 IndexError 而非 DecodeError")
    print("    OK")


def test_sl427_malformed_bcd() -> None:
    """v1.2.5 H2/H3: 非法 BCD 与超小 L 均抛 DecodeError"""
    from sl427 import SL427Decoder
    from sl427.decoder import DecodeError
    from sl651.crc import crc8
    print(">>> SL427 非法BCD/最小L")
    # 地址域含非法 BCD 半字节
    user = bytes([0xC0]) + bytes.fromhex("ABCD020304") + bytes([0x05]) + bytes(4)
    frame = bytes([0x68, len(user), 0x68]) + user + bytes([crc8(user), 0x16])
    try:
        SL427Decoder().decode(frame)
        raise AssertionError("非法 BCD 未报错")
    except DecodeError:
        pass
    # L=6 低于最小用户区长度 7
    user = bytes([0xB4]) + bytes(5)
    frame = bytes([0x68, len(user), 0x68]) + user + bytes([crc8(user), 0x16])
    try:
        SL427Decoder().decode(frame)
        raise AssertionError("L=6 未报错")
    except DecodeError:
        pass
    print("    OK")


def test_tcp_sender_threadsafe() -> None:
    """v1.2.5 H4: 多线程共享 TcpSender 帧不交错"""
    import socket
    import threading
    from simulator.sender import TcpSender
    print(">>> TcpSender 多线程共享")

    received = []

    def server(sock):
        conn, _ = sock.accept()
        conn.settimeout(3)
        buf = b""
        try:
            while True:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass
        received.append(buf)
        conn.close()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    t = threading.Thread(target=server, args=(srv,), daemon=True)
    t.start()

    sender = TcpSender(host="127.0.0.1", port=port, timeout=3)
    payload = "7E7E0102030405060708090A0B0C0D0E"  # 16 字节
    threads = [threading.Thread(target=sender.send, args=(payload, "x"))
               for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    t.join(timeout=5)
    srv.close()
    sender.close()

    data = received[0]
    assert len(data) == 64, f"应收 64 字节，实收 {len(data)}"
    expected = bytes.fromhex(payload)
    for i in range(0, 64, 16):
        assert data[i:i + 16] == expected, f"第 {i // 16} 条帧字节交错/损坏"
    print("    OK")


def test_sl651_hex_type_ff() -> None:
    """v1.2.5 M-3: Hex 型要素首字节 0xFF 不误判负数前缀"""
    from sl651 import SL651Encoder
    print(">>> SL651 Hex型 0xFF 数据")
    enc = SL651Encoder(station_addr="1234567890")
    body = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes
            + bytes([0x4B, 0xF0, 0xF0]) + bytes.fromhex("2306010100")
            + bytes([0xF2, (2 << 3) | 0]) + bytes([0xFF, 0x10]))
    frame = enc.build_frame(0x32, body)
    r = SL651Decoder().decode(frame)
    f2 = [e for e in r.elements if e.code == "F2"]
    assert f2 and f2[0].value == 65296, f"F2 应为 65296，实际 {f2[0].value if f2 else None}"
    print("    OK")


def test_sl651_encoder_validation() -> None:
    """v1.2.5 M-4/M-5/L-7/L-8: SL651 编码器参数校验"""
    from sl651 import SL651Encoder
    from sl651.encoder import EncodeError, _make_def_byte
    print(">>> SL651 编码器参数校验")
    for bad in [(33, 0), (0, 9), (-1, 0)]:
        try:
            _make_def_byte(*bad)
            raise AssertionError(f"_make_def_byte{bad} 未报错")
        except EncodeError:
            pass
    enc = SL651Encoder(station_addr="1234567890")
    try:
        enc.build_hourly_frame([700.0] * 12, 7.0, 12.6)
        raise AssertionError("水位超限未报错")
    except EncodeError:
        pass
    try:
        enc.build_timing_frame([(0x39, -1.5, 1, 1)])
        raise AssertionError("data_len=1 负数未报错")
    except EncodeError:
        pass
    try:
        SL651Encoder(center_addr=300)
        raise AssertionError("center_addr 越界未报错")
    except EncodeError:
        pass
    # v1.2.6 N3: obs_time/tx_time 非 datetime 应抛 EncodeError（非 AttributeError）
    for bad_call in (
        lambda: enc.build_timing_frame([(0x39, 7.0, 4, 3)], obs_time="2026-09-03"),
        lambda: enc.build_alarm_frame([(0x39, 7.0, 4, 3)], obs_time="x"),
        lambda: enc.build_hourly_frame([7.0] * 12, 7.0, 12.6, obs_time=123),
        lambda: enc.build_ascii_frame([("Z", "1.0")], obs_time="x"),
        lambda: enc.build_clock_sync_frame("2026-09-03 12:00"),
    ):
        try:
            bad_call()
            raise AssertionError("非法时间参数未报错")
        except EncodeError:
            pass
    print("    OK")


def test_sl427_encoder_validation() -> None:
    """v1.2.5: SL427 编码器参数校验"""
    from sl427 import SL427Encoder, encode_address, encode_tp
    from sl427.encoder import EncodeError
    from sl427.constants import encode_pw, make_ctrl
    print(">>> SL427 编码器参数校验")
    for kw in [dict(method=1, admin_code=110000, stn_id=70000),
               dict(method=1, admin_code=110000, stn_id=0),
               dict(method=1, admin_code=1000000, stn_id=1),
               dict(method=3),
               dict(method=2, hex_code="ZZZZZZZZ")]:
        try:
            encode_address(**kw)
            raise AssertionError(f"encode_address({kw}) 未报错")
        except EncodeError:
            pass
    try:
        encode_tp(datetime(2101, 1, 1))
        raise AssertionError("年份超界未报错")
    except EncodeError:
        pass
    enc = SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))
    ctrl = make_ctrl(dir_=1, func_code=2)
    try:
        enc.build_frame(0x02, ctrl, data=b"\x00" * 300)
        raise AssertionError("L>255 未报错")
    except EncodeError:
        pass
    try:
        enc.build_frame(0x02, ctrl, tp=b"\x00" * 6)
        raise AssertionError("tp 长度非法未报错")
    except EncodeError:
        pass
    try:
        encode_pw(15, 0)
        raise AssertionError("key1 越界未报错")
    except ValueError:
        pass
    print("    OK")


def test_sl427_ff_tp_strip() -> None:
    """v1.2.5 M-4: AFN=FFH 剥离尾部 Tp 再解析"""
    from sl427 import SL427Decoder, encode_address, encode_tp
    from sl427.constants import make_ctrl
    from sl651.crc import crc8
    print(">>> SL427 AFN=FFH Tp 剥离")
    tp = encode_tp(datetime(2026, 8, 25, 10, 30, 0))
    user = (bytes([make_ctrl(dir_=1, func_code=0x02)])
            + encode_address(method=1, admin_code=110108, stn_id=1284)
            + bytes([0xFF]) + bytes.fromhex("0100") + tp)
    frame = bytes([0x68, len(user), 0x68]) + user + bytes([crc8(user), 0x16])
    r = SL427Decoder().decode(frame)
    times = [e for e in r.elements if e.is_time]
    assert times and "2026-08-25" in times[0].value, "FFH 未正确提取 Tp"
    assert r.crc_ok
    print("    OK")


def test_web_api() -> None:
    """v1.2.5: Web /api/decode 异常路径 + 脱敏 + SL427 字段"""
    print(">>> Web API")
    sys.path.insert(0, str(PROJECT_ROOT / "web"))
    from app import app
    c = app.test_client()
    r = c.post("/api/decode", data="[1,2]", content_type="application/json")
    assert r.status_code == 400, "非对象 JSON 应 400"
    r = c.post("/api/decode", json={"proto": "sl651", "hex": 123})
    assert r.status_code == 400, "非字符串 hex 应 400"
    r = c.post("/api/decode", json={
        "proto": "sl651",
        "hex": "7E7E2500418D23370000320030020C06230601010314F1F100418D23374B"
               "F0F0230601010020190000003B23000378652219000000261900000038121285035AC6"})
    assert r.status_code == 200
    info = dict(r.get_json()["info"])
    assert info.get("密码") == "****", "密码未脱敏"
    r = c.post("/api/decode", json={
        "proto": "sl427", "hex": "681568B40102030405C05545040020700030151412052600AD16"})
    assert r.status_code == 200
    info = dict(r.get_json()["info"])
    assert "帧长度" in info and "用户数据长度" in info, "SL427 缺帧长度字段"
    print("    OK")


def test_cli_json_masking() -> None:
    """v1.2.5: CLI JSON 输出脱敏"""
    import json
    import subprocess
    print(">>> CLI JSON 脱敏")
    out = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "decode_cli.py"), "sl651",
         "--hex", "7E7E2500418D23370000320030020C06230601010314F1F100418D23374B"
                  "F0F0230601010020190000003B23000378652219000000261900000038121285035AC6",
         "-o", "json"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    r0 = json.loads(out.stdout)["results"][0]
    assert r0["password"] == "****"
    assert r0["center_addr"].endswith("**")
    assert r0["station_addr"].endswith("******")
    print("    OK")


def test_simulator_yaml_validation() -> None:
    """v1.2.5: simulate_cli YAML 校验与端口默认值"""
    print(">>> 模拟器配置校验")
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import simulate_cli
    assert simulate_cli.parse_host_port("1.2.3.4", 5001) == ("1.2.3.4", 5001)
    assert simulate_cli.parse_host_port("1.2.3.4:5020", 5001) == ("1.2.3.4", 5020)
    for bad in ["1.2.3.4:abc", ":1883", "1.2.3.4:70000"]:
        try:
            simulate_cli.parse_host_port(bad)
            raise AssertionError(f"parse_host_port({bad!r}) 未报错")
        except ValueError:
            pass
    for bad_addr in ["abc", "123456789G"]:
        try:
            simulate_cli._validate_addr(bad_addr)
            raise AssertionError(f"地址 {bad_addr!r} 未报错")
        except ValueError:
            pass
    for bad_iv in [0, -5, "300"]:
        try:
            simulate_cli._validate_interval(bad_iv)
            raise AssertionError(f"interval {bad_iv!r} 未报错")
        except ValueError:
            pass
    print("    OK")


def test_soil_temp_bounded() -> None:
    """v1.2.5 M-6: 墒情温度有界不漂移"""
    from simulator.generators import SoilMoistureGenerator
    print(">>> 墒情温度有界")
    gen = SoilMoistureGenerator()
    for tick in range(5000):
        _m, temps = gen.next(tick)
    assert all(-30.0 <= t <= 60.0 for t in temps), f"温度越界: {temps}"
    print(f"    5000 步后温度: {temps} OK")


def test_alert_edge_trigger() -> None:
    """v1.2.5 M-7: 雨量加报边沿触发（一次降雨只加报一次）"""
    from simulator.engine import StationRunner
    from simulator import RainStation
    from sl651 import SL651Encoder
    print(">>> 加报边沿触发")

    sent = []

    class FakeSender:
        def send(self, hex_msg, station_addr=""):
            sent.append(hex_msg)
            return True

        def close(self):
            pass

    station = RainStation("1234567892")
    enc = SL651Encoder(station_addr="1234567892", station_type=0x50)
    runner = StationRunner(station, enc, FakeSender(), interval=0.0,
                           enable_alert=True)
    station.rain_gen.raining = True
    station.rain_gen.rain_remaining_minutes = 9999

    # 驱动真实 _run 路径：重写 _stop.wait 让循环执行 3 个周期后停止
    cycles = {"n": 0}

    def fake_wait(_timeout):
        cycles["n"] += 1
        if cycles["n"] >= 3:
            runner._stop.set()

    runner._stop.wait = fake_wait  # type: ignore[method-assign]
    runner._run()

    from sl651 import SL651Decoder
    decoder = SL651Decoder()
    funcs = [decoder.decode_hex(h).function_code for h in sent]
    timing = funcs.count(0x32)
    alarms = funcs.count(0x33)
    assert timing == 3, f"应发送 3 条定时报, 实际 {timing}"
    assert alarms == 1, f"持续降雨应只加报 1 次, 实际 {alarms}"
    print(f"    3 周期: 定时报={timing}, 加报={alarms} OK")


# ---------- v1.2.5 补充修复回归测试（R1~R5） ----------

def test_sl651_decode_entry_check() -> None:
    """v1.2.5 R2: decode(bytes) 入口校验起始符"""
    from sl651.decoder import DecodeError
    print(">>> SL651 decode 入口校验")
    try:
        SL651Decoder().decode(b"\xAA\xBB" + bytes(30))
        raise AssertionError("垃圾起始字节未报错")
    except DecodeError:
        pass
    print("    OK")


def test_sl427_comprehensive_offset() -> None:
    """v1.2.5 R1: 综合参数 0xAA 填充 array 型后偏移正确"""
    from sl427.decoder import _parse_comprehensive
    print(">>> SL427 综合参数填充偏移")
    # bit5=流量(5B, 全AA缺测) + bit6=水位(4B)
    flag = (1 << 5) | (1 << 6)
    data = bytes([flag]) + bytes.fromhex("AAAAAAAAAA") + bytes.fromhex("45230001")
    items = _parse_comprehensive(data)
    names = [i.name for i in items]
    assert "水位" in names, f"水位要素丢失（偏移错位）: {names}"
    print("    OK")


def test_sl427_signed_bcd_invalid_nibble() -> None:
    """v1.2.5 R4: 有符号 BCD 高半字节 0xA~0xE 降级为 '-'"""
    from sl427.decoder import _parse_signed_bcd
    print(">>> SL427 有符号BCD非法半字节")
    val, _raw = _parse_signed_bcd(bytes.fromhex("01B2"), 2)
    assert val == "-", f"应为 '-'，实际 {val}"
    # 正常负值不受影响（高半字节 0xF）
    val, _raw = _parse_signed_bcd(bytes.fromhex("01F2"), 2)
    assert val.startswith("-"), f"应为负值，实际 {val}"
    print("    OK")


def test_sl427_invalid_time_display() -> None:
    """v1.2.5 R5: 非法 BCD 日期显示占位而非假时间"""
    from sl427.decoder import _fmt_time_427
    print(">>> SL427 非法时间显示")
    r = _fmt_time_427(bytes.fromhex("0000002D132600"))  # 日=45 月=19
    assert "无效时间" in r, f"应提示无效时间，实际 {r}"
    r = _fmt_time_427(bytes.fromhex("00301025082600"))
    assert "2026-08-25" in r, f"正常时间解析错误: {r}"
    print("    OK")


def test_sl651_ascii_reserved_id() -> None:
    """v1.2.6 B3: build_ascii_frame 拒绝保留引导符 ST/TT，抛 EncodeError"""
    from sl651.encoder import EncodeError
    print(">>> SL651 ASCII 保留标识符校验")
    enc = SL651Encoder(center_addr=0x01, station_addr="1234567890", password=0, station_type=0x48)
    for bad in ("ST", "TT", "st"):
        try:
            enc.build_ascii_frame([(bad, "1.0")])
            raise AssertionError(f"保留标识符 {bad} 应抛 EncodeError")
        except EncodeError:
            pass
    # 正常标识符不受影响
    frame = enc.build_ascii_frame([("Z", "12.345")])
    assert frame[:1] == b"\x01"
    print("    OK")


def test_sl651_f3_image_display() -> None:
    """v1.2.6 B2: F3 图片要素显示字节摘要而非数值化天文数字"""
    print(">>> SL651 F3 图片显示")
    # 福建 0x36 图片报真实帧（F3 定义符 0xF3 = 30 字节 JPEG 数据）
    hex_frame = (
        "7E7E01100000000600003600F8160040012F7F221205161519F1F1100000000648"
        "F0F02212051615F3F3FFD8FFE000104A46494600010101009000900000FFDB0043"
        "00080606070605080707070909080A0C140D0C0B0B0C1912130F141D1A1F1E1D1A"
        "1C1C20242E2720222C231C1C2837292C30313434341F27393D38323C2E333432FF"
        "DB0043010909090C0B0C180D0D1832211C21323232323232323232323232323232"
        "32323232323232323232323232323232323232323232323232323232323232323232"
        "3232323232FFC00011080015001903012200021101031101FFC4001F0000010501"
        "0101010100000000000000000102030405060708090A0BFFC400B5100002010303"
        "17DA107E"
    )
    r = SL651Decoder().decode_hex(hex_frame)
    f3 = [e for e in r.elements if e.code == "F3"]
    assert f3, "应解析出 F3 图片要素"
    v = str(f3[0].value)
    assert "图片数据" in v and "30 字节" in v, f"F3 应显示字节摘要: {v}"
    assert "e+" not in v.lower(), f"F3 不应数值化: {v}"
    print("    OK")


def test_sl427_invalid_nibble_time() -> None:
    """v1.2.6 B1: 非法 BCD 半字节（落入合法范围的假时间）显示占位"""
    from sl427.decoder import _fmt_time_427
    print(">>> SL427 非法半字节时间显示")
    # 秒=0x5A：or 0 静默归零后落入合法范围，旧版显示 "14:15:00" 假时间
    r = _fmt_time_427(bytes.fromhex("5A151412052600"))
    assert "无效时间" in r, f"非法半字节应提示无效时间，实际 {r}"
    # 月=0x1A（非法半字节）
    r = _fmt_time_427(bytes.fromhex("003010251A2600"))
    assert "无效时间" in r, f"非法半字节应提示无效时间，实际 {r}"
    # 合法的 0 值字段不受影响（秒=0x00 合法）
    r = _fmt_time_427(bytes.fromhex("00151412052600"))
    assert "2026-05-12 14:15:00" in r, f"合法 0 秒解析错误: {r}"
    print("    OK")


# ---------- v1.2.7 审计 v2.2 缺陷回归测试 ----------

def test_sl651_uniform_report() -> None:
    """C-1: 0x31 均匀报数据组重复格式（标识符组一次 + 多组数据）"""
    print(">>> SL651 0x31 均匀报数据组")
    hex_frame = (
        "7E7E011000000006000031004E022F7E221205110019F1F1100000000648F0F02212"
        "0510050418000005392300028960000289600002896000028960000289600002896"
        "0000289600002896000028960000289600002896000028960035B947E"
    )
    r = SL651Decoder().decode_hex(hex_frame)
    assert r.crc_ok and r.function_code == 0x31
    wl = [e for e in r.elements if e.code == "39"]
    assert len(wl) == 12, f"应解析 12 组水位, 实际 {len(wl)}"
    assert all(_value_eq(e.value, 28.96) for e in wl), \
        f"水位值应为 28.96: {[e.value for e in wl]}"
    assert r.elements[0].code == "04" and r.elements[0].value == 5
    print(f"    时间步长+12 组水位 OK (共 {len(r.elements)} 要素)")


def test_sl651_f5_fixed_length() -> None:
    """M-1: F5 定义符失配时按规范固定 24B 解析，不产生垃圾要素"""
    print(">>> SL651 F5 固定长度解析")
    hex_frame = (
        "7E7E100012345678123434003A020003140612020000F1F1001234567848F0F01406"
        "120200F55C0AAA0AAAFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF391A002730"
        "3812129003ADF77E"
    )
    r = SL651Decoder().decode_hex(hex_frame)
    assert r.crc_ok
    f5 = [e for e in r.elements if e.code == "F5"]
    assert len(f5) == 12, f"F5 应解析 12 组, 实际 {len(f5)}"
    assert not any(e.code in ("2D", "0A", "EC") for e in r.elements), \
        f"不应出现垃圾要素: {[e.code for e in r.elements]}"
    assert any("F5" in w for w in r.warnings), f"应记录定义符失配告警: {r.warnings}"
    print(f"    F5=12 组, 告警={r.warnings} OK")


def test_sl427_84_no_tp() -> None:
    """M-2: AFN=84H 自报帧数据域仅 2B 电压（规范表B.98 无 Tp），API 不再声明 tp"""
    print(">>> SL427 AFN=0x84 自报帧无 Tp")
    from sl427 import SL427Encoder, SL427Decoder, encode_address
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    f = enc.build_self_report_84(voltage=12.3)
    r = SL427Decoder().decode(f)
    assert r.crc_ok and r.afn == 0x84
    assert len(r.elements) == 1, f"应仅 1 个电压要素: {[e.name for e in r.elements]}"
    assert r.elements[0].name == "电压"
    assert abs(float(r.elements[0].value) - 12.3) < 0.01
    assert not any(e.name == "观测时间" for e in r.elements), "84H 自报帧不应含 Tp"
    print(f"    {r.elements[0].value}V (无 Tp) OK")


def test_sl651_bcd_overflow_contract() -> None:
    """M-3: SL651 BCD 超限统一抛 EncodeError"""
    print(">>> SL651 BCD 超限异常契约")
    from sl651.encoder import EncodeError
    enc = SL651Encoder(center_addr=1, station_addr="00418D2337")
    try:
        enc.build_timing_frame([(0x39, 123456789.0, 4, 3)])
        raise AssertionError("BCD 超限应抛 EncodeError")
    except EncodeError:
        pass
    print("    OK")


def test_sl427_bcd_overflow_contract() -> None:
    """M-3: SL427 BCD 超限统一抛 EncodeError"""
    print(">>> SL427 BCD 超限异常契约")
    from sl427 import SL427Encoder, encode_address
    from sl427.encoder import EncodeError
    enc = SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))
    for fn in (lambda: enc.build_self_report_84(voltage=999.99),
               lambda: enc.build_set_recharge(amount=-1),
               lambda: enc.build_param_set_frame(0x10, 0x00, b"\x01", pw=1000)):
        try:
            fn()
            raise AssertionError("超限应抛 EncodeError")
        except EncodeError:
            pass
    print("    OK")


def test_sl651_body_len_limit() -> None:
    """M-5: 正文长度 >4095 抛 EncodeError，不再静默掩码"""
    print(">>> SL651 正文长度上限")
    from sl651.encoder import EncodeError
    enc = SL651Encoder(center_addr=1, station_addr="00418D2337")
    try:
        enc.build_frame(0x32, b"\x00" * 5000)
        raise AssertionError("正文超限应抛 EncodeError")
    except EncodeError:
        pass
    try:
        enc.build_ascii_frame([("Z", "1.0")] * 2000)
        raise AssertionError("ASCII 正文超限应抛 EncodeError")
    except EncodeError:
        pass
    print("    OK")


def test_sl427_short_data_degrade() -> None:
    """L-3: C0 短数据域不再静默返回 0 要素"""
    print(">>> SL427 C0 短数据域降级")
    from sl427 import SL427Encoder, SL427Decoder, encode_address
    from sl427 import constants as SC
    from sl651.bcd import int_to_bcd_bytes
    enc = SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))
    data = bytes(reversed(int_to_bcd_bytes(12345, 4)))
    f = enc.build_frame(0xC0, SC.make_ctrl(dir_=1, func_code=0x02), data)
    r = SL427Decoder().decode(f)
    assert r.crc_ok
    assert len(r.elements) > 0, "短数据域不应静默返回 0 要素"
    assert any("降级" in w for w in r.warnings), f"应记录降级告警: {r.warnings}"
    print(f"    短数据域解析 {len(r.elements)} 要素, 告警={r.warnings} OK")


def test_sl427_addr_method() -> None:
    """L-4: 地址方式判定（方式1 省码 11~82，BYTE1=00H 为方式2）"""
    print(">>> SL427 地址方式判定")
    from sl427.decoder import _format_addr
    a1 = _format_addr(bytes.fromhex("1101080405"))
    assert a1.startswith("方式1"), f"应为方式1: {a1}"
    assert "110108" in a1 and "1284" in a1, f"行政区划/站址错误: {a1}"
    a2 = _format_addr(bytes.fromhex("0012345678"))
    assert a2.startswith("方式2"), f"应为方式2: {a2}"
    print(f"    {a1} | {a2} OK")


def test_sl651_downlink_queries() -> None:
    """无参数体的下行查询帧（37/44/45/46/50/51H，结束符 ENQ）"""
    print(">>> SL651 下行查询帧补全")
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", station_type=0x48)
    cases = [
        (enc.build_query_frame, 0x37),
        (enc.build_query_pump_data, 0x44),
        (enc.build_query_software_version, 0x45),
        (enc.build_query_status_alarm, 0x46),
        (enc.build_query_event_record, 0x50),
        (enc.build_query_clock, 0x51),
    ]
    for builder, fc in cases:
        frame = builder()
        assert frame[-3] == 0x05, f"0x{fc:02X} 结束符应为 ENQ"
        r = SL651Decoder().decode(frame)
        assert r.crc_ok, f"0x{fc:02X} CRC 应通过"
        assert r.function_code == fc, f"功能码应为 0x{fc:02X}, 实际 0x{r.function_code:02X}"
        assert r.direction == 1, f"0x{fc:02X} 应为下行"
    print(f"    {len(cases)} 个下行查询帧 OK")


def test_sl651_config_and_manual_frames() -> None:
    """42H 修改运行参数 / 41H·43H 读取配置 / 0x35 人工置数报"""
    print(">>> SL651 配置读取/修改与人工置数报")
    from sl651.encoder import EncodeError
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", station_type=0x48)

    # 42H 参数设置（复用 40H 正文）
    f42 = enc.build_set_param_frame([(0x39, 12.345, 4, 3)], function_code=0x42)
    r42 = SL651Decoder().decode(f42)
    assert r42.crc_ok and r42.function_code == 0x42 and r42.direction == 1
    assert f42[-3] == 0x05, "结束符应为 ENQ"

    # 41H / 43H 读取配置（参数标识符列表）
    f41 = enc.build_read_config_frame([0x01, 0x02])
    r41 = SL651Decoder().decode(f41)
    assert r41.crc_ok and r41.function_code == 0x41 and r41.direction == 1
    f43 = enc.build_read_config_frame([0x01], function_code=0x43)
    r43 = SL651Decoder().decode(f43)
    assert r43.crc_ok and r43.function_code == 0x43

    # 0x35 人工置数报（上行，F2 标识符 + 原编码数据）
    f35 = enc.build_manual_frame(bytes.fromhex("0102030405"))
    r35 = SL651Decoder().decode(f35)
    assert r35.crc_ok and r35.function_code == 0x35 and r35.direction == 0
    try:
        enc.build_manual_frame(b"")
        raise AssertionError("空人工置数应抛 EncodeError")
    except EncodeError:
        pass
    print("    42H/41H/43H/35H OK")


def test_sl651_init_storage_and_password() -> None:
    """47H 初始化固态存储（97H 标识符）/ 49H 修改密码（03H 标识符）"""
    print(">>> SL651 47H/49H")
    from sl651.encoder import EncodeError
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", station_type=0x48)

    f47 = enc.build_init_solid_storage()
    r47 = SL651Decoder().decode(f47)
    assert r47.crc_ok and r47.function_code == 0x47 and r47.direction == 1
    assert f47[22:-3] == b"\x97", f"47H 数据域应为 97H: {f47[22:-3].hex()}"

    f49 = enc.build_change_password_frame(0x1234, 0x5678)
    r49 = SL651Decoder().decode(f49)
    assert r49.crc_ok and r49.function_code == 0x49 and r49.direction == 1
    assert f49[22:-3] == bytes.fromhex("031234035678"), f49[22:-3].hex()

    try:
        enc.build_change_password_frame(0x10000, 0)
        raise AssertionError("密码超限应抛 EncodeError")
    except EncodeError:
        pass
    print("    47H 97H 标识符 / 49H 新旧密码 OK")


def test_sl651_test_frame() -> None:
    """0x30 测试报编码（正文同定时报，规约表28）"""
    print(">>> SL651 0x30 测试报编码")
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", station_type=0x48)
    frame = enc.build_test_frame([(0x39, 12.345, 4, 3)],
                                 obs_time=datetime(2026, 9, 14, 10, 0))
    r = SL651Decoder().decode(frame)
    assert r.crc_ok and r.function_code == 0x30, f"0x{r.function_code:02X}"
    wl = [e for e in r.elements if e.code == "39"]
    assert wl and abs(float(wl[0].value) - 12.345) < 0.001, r.elements
    print("    0x30 测试报编解码 OK")


def test_sl651_ascii_uniform() -> None:
    """0x31 ASCII 均匀报：时间步长码 DRxnn + 单标识符多值数组"""
    print(">>> SL651 0x31 ASCII 均匀报")
    from sl651 import constants as C
    body_ascii = (
        "ST 1000000006 48 TT 2205100500 DRN05 005 "
        "DRZ1 28.96 28.96 28.97 28.98 28.99 29.00 "
        "29.01 29.02 29.03 29.04 29.05 29.06"
    ).encode("ascii")
    body = b"0001" + b"220510050000" + body_ascii
    body_len = 4 + 12 + len(body_ascii)
    ident_hi = (0 << 7) | ((body_len >> 8) & 0x0F)
    frame = bytearray([C.SOH])
    frame.extend(b"01" + b"1000000006" + b"0000" + b"31")
    frame.extend(f"{ident_hi:02X}{body_len & 0xFF:02X}".encode("ascii"))
    frame.append(C.STX)
    frame.extend(body)
    frame.append(C.ETX)
    frame.extend(f"{crc16(bytes(frame)):04X}".encode("ascii"))

    r = SL651Decoder().decode(bytes(frame))
    assert r.crc_ok and r.function_code == 0x31 and r.encoding == "ASCII"
    ts = [e for e in r.elements if e.code == "DRN05"]
    assert ts and ts[0].value == 5, f"时间步长码未识别: {[e.code for e in r.elements]}"
    assert "分钟" in ts[0].name, f"步长单位错误: {ts[0].name}"
    wl = [e for e in r.elements if e.code == "DRZ1"]
    assert len(wl) == 12, f"应解析 12 组水位, 实际 {len(wl)}"
    assert _value_eq(wl[0].value, 28.96) and _value_eq(wl[-1].value, 29.06)
    print(f"    时间步长+{len(wl)} 组水位 OK")


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
        test_sl651_ascii_roundtrip,
        test_fujian_messages,
        test_simulator_engine_smoke, test_hourly_frame_validation, test_recharge_le_bcd,
        test_beijing_messages,
        test_negative_bcd, test_invalid_bcd_graceful,
        test_sl651_truncated_uplink, test_sl427_malformed_bcd,
        test_tcp_sender_threadsafe, test_sl651_hex_type_ff,
        test_sl651_encoder_validation, test_sl427_encoder_validation,
        test_sl427_ff_tp_strip, test_web_api, test_cli_json_masking,
        test_simulator_yaml_validation, test_soil_temp_bounded,
        test_alert_edge_trigger,
        test_sl651_decode_entry_check, test_sl427_comprehensive_offset,
        test_sl427_signed_bcd_invalid_nibble, test_sl427_invalid_time_display,
        test_sl427_invalid_nibble_time, test_sl651_f3_image_display,
        test_sl651_ascii_reserved_id,
        test_sl651_uniform_report, test_sl651_f5_fixed_length,
        test_sl427_84_no_tp, test_sl651_bcd_overflow_contract,
        test_sl427_bcd_overflow_contract, test_sl651_body_len_limit,
        test_sl427_short_data_degrade, test_sl427_addr_method,
        test_sl651_ascii_uniform, test_sl651_test_frame,
        test_sl651_downlink_queries, test_sl651_config_and_manual_frames,
        test_sl651_init_storage_and_password,
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
