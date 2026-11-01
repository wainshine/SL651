#!/usr/bin/env python3
"""v1.4.0 协议契约/边界回归测试（审计 v2.5/v2.6/补充 L-12~L-17）。"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sl651 import SL651Decoder, SL651Encoder
from sl651.bcd import datetime_to_bcd
from sl651.errors import DecodeError, EncodeError, ProtocolError
from sl427 import SL427Decoder, SL427Encoder, encode_address, make_ctrl

FAILURES: list[str] = []


def _expect_encode_error(fn, label: str) -> None:
    try:
        fn()
    except EncodeError:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"{label} 泄漏 {type(e).__name__}: {e}") from e
    raise AssertionError(f"{label} 未抛 EncodeError")


def _enc427() -> SL427Encoder:
    return SL427Encoder(encode_address(1, 110108, 1284))


def test_exception_identity() -> None:
    from sl651.decoder import DecodeError as D2
    from sl651.encoder import EncodeError as E2
    from sl427.decoder import DecodeError as D3
    from sl427.encoder import EncodeError as E3
    assert EncodeError is E2 is E3
    assert DecodeError is D2 is D3
    assert issubclass(EncodeError, ProtocolError)
    print("    4 个异常类别名同一性 OK")


def test_encoder_invalid_inputs() -> None:
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", password=0, station_type=0x48)
    cases = [
        (lambda: enc.build_timing_frame([(0x1FF, 1.0, 2, 1)]), "guide 0x1FF"),
        (lambda: enc.build_timing_frame([(-1, 1.0, 2, 1)]), "guide -1"),
        (lambda: enc.build_timing_frame([(0x39, float("nan"), 4, 3)]), "NaN"),
        (lambda: enc.build_timing_frame([(0x39, float("inf"), 4, 3)]), "inf"),
        (lambda: enc.build_timing_frame([(0x39, "1.0", 4, 3)]), "str value"),
        (lambda: enc.build_timing_frame([(0x39, 1.0, 4, 3)], obs_time=datetime(1999, 1, 1)), "year 1999"),
        (lambda: enc.build_timing_frame([(0x39, 1.0, 4, 3)], obs_time=datetime(2100, 1, 1)), "year 2100"),
        (lambda: enc.build_frame(0x32, b"", direction=2), "direction 2"),
        (lambda: enc.build_frame(0x32, b"", end_marker=0x1FF), "end_marker 0x1FF"),
    ]
    for fn, label in cases:
        _expect_encode_error(fn, label)

    e427 = _enc427()
    _expect_encode_error(lambda: e427.build_heartbeat(-1), "heartbeat -1")
    _expect_encode_error(lambda: e427.build_heartbeat(0x00), "heartbeat 0x00")
    for mode in (-1, 4, 255):
        _expect_encode_error(lambda m=mode: e427.build_set_work_mode(m), f"mode {mode}")
    _expect_encode_error(lambda: e427.build_self_report_84(100), "voltage 100")
    _expect_encode_error(lambda: e427.build_self_report_84(float("nan")), "voltage NaN")
    _expect_encode_error(lambda: e427.build_self_report_c0(0x02, b"\x00" * 4, alarm=-1), "alarm -1")
    _expect_encode_error(lambda: e427.build_query_response(0x01, b"\x00" * 3, state=70000), "state 70000")
    print("    SL651/SL427 非法输入全部 EncodeError OK")


def test_hourly_bounds_and_def_byte() -> None:
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", password=0, station_type=0x48)
    body = enc.build_hourly_body([None] * 12, 1.0, 12.0, obs_time=datetime(2026, 1, 1))
    assert body[body.index(0xF5) + 1] == 0xC0, "F5 定义符应为 0xC0（0 位小数）"
    _expect_encode_error(
        lambda: enc.build_hourly_body([-1.0] * 12, 1.0, 12.0), "负水位")
    _expect_encode_error(
        lambda: enc.build_hourly_body([655.35] * 12, 1.0, 12.0), "水位 655.35")
    _expect_encode_error(
        lambda: enc.build_hourly_body([1.0] * 12, 1.0, 12.0,
                                      rain_amounts=[25.5] * 12), "雨量 25.5")
    _expect_encode_error(
        lambda: enc.build_hourly_body([1.0] * 12, 1.0, 12.0,
                                      rain_amounts=[-0.1] * 12), "负雨量")
    # 合法边界
    body = enc.build_hourly_body([655.34] * 12, 1.0, 12.0,
                                 rain_amounts=[25.4] * 12,
                                 obs_time=datetime(2026, 1, 1))
    r = SL651Decoder().decode(enc.build_frame(0x34, body))
    assert r.crc_ok
    print("    小时报边界/F5 定义符 OK")


def test_address_roundtrip() -> None:
    for admin in (110000, 110105, 710000, 820000):
        addr = encode_address(1, admin, 123)
        enc = SL427Encoder(addr)
        r = SL427Decoder().decode(enc.build_heartbeat())
        assert "方式1" in r.addr_display, (admin, r.addr_display)
    for bad in (0, 9999, 100000, 830000, 1000000):
        _expect_encode_error(lambda b=bad: encode_address(1, b, 1), f"admin_code {bad}")
    default = SL427Encoder()
    r = SL427Decoder().decode(default.build_heartbeat())
    assert "方式1" in r.addr_display, r.addr_display
    print("    地址方式 1 往返/边界 OK")


def test_a_pad_bcd() -> None:
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", password=0, station_type=0x48)
    frame = enc.build_set_param_frame(
        [(0x05, 13812345678, 6, 0)], a_pad_guides={0x05})
    r = SL651Decoder().decode(frame)
    elems = [e for e in r.elements if e.code == "05"]
    assert elems and elems[0].value == 13812345678, [(e.code, e.value) for e in r.elements]
    assert any("A 补齐" in w for w in r.warnings), r.warnings

    # 非配置帧路径仍拒绝 A 补齐
    body = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes + bytes([0x4B, 0xF0, 0xF0])
            + bytes.fromhex("2601010100") + bytes([0x05, 0x30])
            + bytes.fromhex("A13812345678"))
    r2 = SL651Decoder().decode(enc.build_frame(0x32, body))
    elems2 = [e for e in r2.elements if e.code == "05"]
    assert elems2 and elems2[0].value == "-", [(e.code, e.value) for e in r2.elements]
    print("    A 补齐 BCD（仅 40H~43H）OK")


def test_comprehensive_and_fill() -> None:
    enc = _enc427()
    # bit5 流量(AA×5) + bit6 水位 + bit7 雨量
    payload = (bytes([0xE0]) + b"\xAA" * 5
               + bytes.fromhex("45230001") + bytes.fromhex("001000")
               + b"\x00" * 4)
    frame = enc.build_frame(0xB0, make_ctrl(1, 0x0E), payload)
    r = SL427Decoder().decode(frame)
    by_name = {e.name: e for e in r.elements}
    assert by_name["流量/水量"].value == "-", by_name["流量/水量"].value
    assert by_name["水位"].raw != by_name["雨量"].raw
    assert by_name["水位"].value != by_name["雨量"].value

    # 标量填充不再静默省略
    frame2 = enc.build_frame(0xB0, make_ctrl(1, 0x01), b"\xAA" * 3 + b"\x00" * 4)
    r2 = SL427Decoder().decode(frame2)
    assert r2.elements and r2.elements[0].name == "雨量" and r2.elements[0].value == "-"

    # 信道 0xFF/0xAA 降级为“无”
    for fill in (b"\xFF", b"\xAA"):
        frame3 = enc.build_frame(0x65, make_ctrl(1, 0x00),
                                 b"\x01" + b"\x00" * 7 + fill)
        r3 = SL427Decoder().decode(frame3)
        ch = [e for e in r3.elements if e.name == "备用信道"]
        assert ch and ch[0].value == "无", ch
    print("    综合参数/标量填充/信道 0xFF OK")


def test_0d_contexts() -> None:
    enc = _enc427()
    tp = bytes.fromhex("00300002112600")

    def c0(data: bytes):
        return SL427Decoder().decode(
            enc.build_frame(0xC0, make_ctrl(1, 0x0D), data))

    r = c0(bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200") + tp)
    assert any(e.value == "12.60" for e in r.elements), [(e.name, e.value) for e in r.elements]

    r = c0(bytes.fromhex("0100") + bytes.fromhex("0200"))
    assert not any(e.name == "电压/报警状态" for e in r.elements), [(e.name, e.value) for e in r.elements]
    assert any("C0" in w for w in r.warnings)

    r = c0(bytes.fromhex("01000000") + bytes.fromhex("0100")
           + bytes.fromhex("0200") + tp)
    assert not any(e.name == "电压/报警状态" for e in r.elements)
    assert any("0x0D" in w for w in r.warnings)

    r = SL427Decoder().decode(enc.build_query_response(
        0x0D, bytes.fromhex("6012"), alarm=1, state=2))
    assert any(e.value == "12.60" for e in r.elements)

    r = SL427Decoder().decode(enc.build_self_report_84(12.34))
    assert any(e.value == "12.34" for e in r.elements)
    print("    0x0D 上下文矩阵 OK")


def test_45h_reserved_bits() -> None:
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", password=0, station_type=0x4B)
    obs = datetime_to_bcd(datetime(2026, 1, 1))[:5]
    body = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes + bytes([0x4B, 0xF0, 0xF0])
            + obs + bytes([0x45, 0x20]) + bytes.fromhex("00001000"))
    r = SL651Decoder().decode(enc.build_frame(0x32, body))
    assert any("保留位" in w for w in r.warnings), r.warnings
    assert len([e for e in r.elements if e.code.startswith("BIT")]) == 12
    body0 = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes + bytes([0x4B, 0xF0, 0xF0])
             + obs + bytes([0x45, 0x20]) + bytes.fromhex("00000000"))
    r0 = SL651Decoder().decode(enc.build_frame(0x32, body0))
    assert not any("保留位" in w for w in r0.warnings), r0.warnings
    print("    45H 位宽/保留位 OK")


def test_cli_masking() -> None:
    sample = ("7E7E2500418D23370000320030020C06230601010314F1F100418D23374B"
              "F0F0230601010020190000003B23000378652219000000261900000038121285035AC6")
    cli = PROJECT_ROOT / "tools" / "decode_cli.py"
    out = subprocess.run([sys.executable, str(cli), "sl651", "--hex", sample],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "7E7E…" in out.stdout and sample not in out.stdout, "text 输出泄漏完整报文"
    assert "中心站地址    : **" in out.stdout, out.stdout
    assert "00********" in out.stdout, out.stdout

    out_raw = subprocess.run([sys.executable, str(cli), "sl651", "--hex", sample, "--show-raw"],
                             capture_output=True, text=True)
    assert sample in out_raw.stdout, "--show-raw 应显示完整报文"

    bad = subprocess.run(
        [sys.executable, str(cli), "sl651", "--hex", "7E7E0100000000000000DEAD0032", "-o", "json"],
        capture_output=True, text=True)
    data = json.loads(bad.stdout)
    assert bad.returncode == 2
    assert data["errors"] and "7E7E…" in data["errors"][0]["message"]
    assert "7E7E0100000000000000DEAD0032" not in bad.stdout
    print("    CLI 脱敏/--show-raw OK")


def test_simulator_config_validators() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import simulate_cli
    assert simulate_cli._validate_function_code("0x33") == 0x33
    assert simulate_cli._validate_function_code(0x32) == 0x32
    for bad in (33, "0x34", "abc", True, 1.5):
        try:
            simulate_cli._validate_function_code(bad)
            raise AssertionError(f"function_code {bad!r} 应拒绝")
        except ValueError:
            pass
    assert simulate_cli._validate_alert_threshold(0.05) == 0.05
    for bad in (-1, "x", float("nan")):
        try:
            simulate_cli._validate_alert_threshold(bad)
            raise AssertionError(f"alert_threshold {bad!r} 应拒绝")
        except ValueError:
            pass
    print("    YAML function_code/alert_threshold 校验 OK")


def test_tcp_sender_reconnect_sleep_outside_lock() -> None:
    import simulator.sender as sender_mod
    snd = sender_mod.TcpSender("127.0.0.1", 1, timeout=0.05,
                               reconnect=True, reconnect_delay=0.05)
    orig_sleep = sender_mod.time.sleep
    violations = []

    def fake_sleep(seconds):
        if snd._lock.locked():
            violations.append(seconds)
        orig_sleep(0)

    sender_mod.time.sleep = fake_sleep
    try:
        assert snd.send("00") is False
    finally:
        sender_mod.time.sleep = orig_sleep
    assert not violations, "重连等待不应持有 TcpSender._lock"
    print("    TcpSender 重连等待在锁外 OK")


def test_false_length_resync() -> None:
    """v2.5 M-3 / v2.6 feed: 谎报长度不得阻塞后续合法帧。"""
    enc651 = SL651Encoder(center_addr=1, station_addr="1234567890",
                          password=0, station_type=0x48)
    good651 = enc651.build_timing_frame([(0x39, 1.0, 4, 3)])
    bad651 = b"\x7E\x7E" + b"\x00" * 9 + b"\xFF\xFF" + b"\x02" + b"\x00" * 3
    d651 = SL651Decoder()
    out = d651.feed(bad651 + good651)
    assert len(out) == 1 and out[0].crc_ok, f"SL651 谎报长度阻塞: {len(out)}"

    enc427 = _enc427()
    good427 = enc427.build_heartbeat()
    bad427 = b"\x68\xFF\x68" + b"\x00" * 3
    d427 = SL427Decoder()
    out = d427.feed(bad427 + good427)
    assert len(out) == 1, f"SL427 谎报长度阻塞: {len(out)}"
    print("    谎报长度重同步 OK")


def main() -> int:
    print("=" * 60)
    print("协议契约/边界回归测试")
    print("=" * 60)
    tests = [
        ("异常同一性", test_exception_identity),
        ("编码器非法输入", test_encoder_invalid_inputs),
        ("小时报边界", test_hourly_bounds_and_def_byte),
        ("地址往返", test_address_roundtrip),
        ("A 补齐 BCD", test_a_pad_bcd),
        ("填充/综合参数/信道", test_comprehensive_and_fill),
        ("0x0D 上下文", test_0d_contexts),
        ("45H 保留位", test_45h_reserved_bits),
        ("CLI 脱敏", test_cli_masking),
        ("模拟器配置校验", test_simulator_config_validators),
        ("TcpSender 锁外等待", test_tcp_sender_reconnect_sleep_outside_lock),
        ("谎报长度重同步", test_false_length_resync),
    ]
    for name, fn in tests:
        print(f">>> {name}")
        try:
            fn()
        except Exception as e:
            print(f"    ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            FAILURES.append(f"{name}: {e}")
    print()
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("✅ 契约测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
