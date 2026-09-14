#!/usr/bin/env python3
"""SL427 参数设置便捷方法 (AFN=16H~20H) 数据域编码测试。

按规约 7.2.6~7.2.16 / 表14~表21 校验字节布局（含小端 BCD、符号位、单位位）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl427 import SL427Decoder, SL427Encoder, encode_address
from sl427.encoder import EncodeError

FAILURES: list[str] = []


def _enc() -> SL427Encoder:
    return SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))


def _extract(frame: bytes, data_len: int) -> tuple[int, bytes]:
    """从命令帧提取 (AFN, 数据域 D)。这些 AFN 的 AUX = PW(2B)+Tp(7B)。"""
    assert frame[0] == 0x68 and frame[2] == 0x68 and frame[-1] == 0x16, \
        f"帧边界错误: {frame.hex().upper()}"
    L = frame[1]
    user = frame[3:3 + L]
    assert len(user) == 16 + data_len, \
        f"L={L} 与数据域 {data_len}B 不符 (user={len(user)})"
    afn = user[6]
    data = user[7:7 + data_len]
    return afn, bytes(data)


def _check_crc(frame: bytes) -> None:
    r = SL427Decoder().decode(frame)
    assert r.crc_ok, f"CRC 应通过: {frame.hex().upper()}"


def test_16h_recharge_alarm() -> None:
    frame = _enc().build_set_recharge_alarm(123456)
    _check_crc(frame)
    afn, data = _extract(frame, 3)
    assert afn == 0x16
    assert data == bytes.fromhex("563412"), data.hex()  # 低位在前
    print("    16H 剩余水量报警值 OK")


def test_17h_level_limits() -> None:
    enc = _enc()
    frame = enc.build_set_level_limits([(5.5, 0.1, 99.99)])
    _check_crc(frame)
    afn, data = _extract(frame, 7)
    assert afn == 0x17
    assert data == bytes.fromhex("5005001000 9999".replace(" ", "")), data.hex()
    # 负基值符号位：第3字节 D7=1
    frame = enc.build_set_level_limits([(-5.5, 0.0, 1.0)])
    _, data = _extract(frame, 7)
    assert data[2] & 0x80 == 0x80, data.hex()
    print("    17H 水位基值/上下限 OK")


def test_18h_pressure_limits() -> None:
    frame = _enc().build_set_pressure_limits([(100.5, 0.0)])
    _check_crc(frame)
    afn, data = _extract(frame, 8)
    assert afn == 0x18
    assert data == bytes.fromhex("50000100" + "00000000"), data.hex()
    print("    18H 水压上/下限 OK")


def test_19h_water_quality() -> None:
    frame = _enc().build_set_water_quality(0x19, [(0, 12345), (1, 6789)])
    _check_crc(frame)
    afn, data = _extract(frame, 5 + 2 * 4)
    assert afn == 0x19
    assert data[:5] == bytes.fromhex("0300000000"), data.hex()  # 位图 bit0/bit1
    assert data[5:9] == bytes.fromhex("45230100")
    assert data[9:13] == bytes.fromhex("89670000")
    # 下限 AFN=1AH
    frame = _enc().build_set_water_quality(0x1A, [(2, 100)])
    assert _extract(frame, 5 + 4)[0] == 0x1A
    print("    19H/1AH 水质参数 OK")


def test_1bh_water_amount() -> None:
    frame = _enc().build_set_water_amount([1234567890])
    _check_crc(frame)
    afn, data = _extract(frame, 5)
    assert afn == 0x1B
    assert data == bytes.fromhex("9078563412"), data.hex()
    print("    1BH 水量初始值 OK")


def test_1ch_relay_code_len() -> None:
    frame = _enc().build_set_relay_code_len(120)
    _check_crc(frame)
    afn, data = _extract(frame, 1)
    assert afn == 0x1C and data == bytes([120])
    print("    1CH 中继引导码长值 OK")


def test_1dh_relay_addr() -> None:
    a = encode_address(method=1, admin_code=110108, stn_id=1284)
    b = encode_address(method=2, hex_code="12345678")
    frame = _enc().build_set_relay_addr([a, b])
    _check_crc(frame)
    afn, data = _extract(frame, 10)
    assert afn == 0x1D and data == a + b
    print("    1DH 中继转发地址 OK")


def test_1eh_relay_auto_switch() -> None:
    frame = _enc().build_set_relay_auto_switch(0x1C)
    _check_crc(frame)
    afn, data = _extract(frame, 1)
    assert afn == 0x1E and data == bytes([0x1C])
    print("    1EH 中继自动切换/自报 OK")


def test_1fh_flow_limits() -> None:
    enc = _enc()
    frame = enc.build_set_flow_limits([(123.456, False)])
    _check_crc(frame)
    afn, data = _extract(frame, 5)
    assert afn == 0x1F
    assert data == bytes.fromhex("5634120000"), data.hex()
    # 负值 + m³/h：BYTE5 高半字节 = 11(负) 11(单位)
    _, data = _extract(enc.build_set_flow_limits([(-1.5, True)]), 5)
    assert data[4] == 0xF0, data.hex()
    print("    1FH 流量参数上限 OK")


def test_20h_report_threshold() -> None:
    frame = _enc().build_set_report_threshold(category=0, index=1,
                                              interval_min=5, threshold=0.5)
    _check_crc(frame)
    afn, data = _extract(frame, 3)
    assert afn == 0x20
    assert data == bytes.fromhex("010505"), data.hex()
    print("    20H 启报阈值/固态间隔 OK")


def test_validation_errors() -> None:
    enc = _enc()
    bad_calls = [
        lambda: enc.build_set_recharge_alarm(1000000),
        lambda: enc.build_set_level_limits([(9000.0, 0, 0)]),
        lambda: enc.build_set_pressure_limits([(1000000.0, 0)]),
        lambda: enc.build_set_water_quality(0x18, [(0, 1)]),
        lambda: enc.build_set_water_quality(0x19, [(40, 1)]),
        lambda: enc.build_set_water_amount([-1]),
        lambda: enc.build_set_relay_code_len(256),
        lambda: enc.build_set_relay_addr([b"\x01\x02"]),
        lambda: enc.build_set_relay_auto_switch(256),
        lambda: enc.build_set_flow_limits([(1e9, False)]),
        lambda: enc.build_set_report_threshold(16, 0, 5, 0.5),
        lambda: enc.build_set_report_threshold(0, 0, 0, 0.5),
        lambda: enc.build_set_report_threshold(0, 0, 5, 10.0),
    ]
    for i, fn in enumerate(bad_calls):
        try:
            fn()
            raise AssertionError(f"第{i}个超限调用未抛 EncodeError")
        except EncodeError:
            pass
    print(f"    {len(bad_calls)} 项超限校验 OK")


def test_10h_set_addr_validation() -> None:
    """AFN=10H 设置地址数据域固定 5B（审计 v2.3 M-4）。"""
    enc = _enc()
    frame = enc.build_set_addr(bytes.fromhex("0102030405"))
    _check_crc(frame)
    afn, data = _extract(frame, 5)
    assert afn == 0x10 and data == bytes.fromhex("0102030405"), (afn, data.hex())
    for bad in (b"", b"\x01", bytes(4), bytes(6)):
        try:
            enc.build_set_addr(bad)
            raise AssertionError(f"长度 {len(bad)} 应抛 EncodeError")
        except EncodeError:
            pass
    print("    10H 地址长度校验 OK")


def test_a2h_channel_validation() -> None:
    """AFN=A2H 信道地址长度按类型码校验（审计 v2.3 M-4）。"""
    enc = _enc()
    enc.build_set_channel(0x01, bytes(7))   # 短信 7B
    enc.build_set_channel(0x02, bytes(7))   # IPV4 7B
    enc.build_set_channel(0x03, bytes(3))   # 北斗 3B
    bad_cases = [
        (0x01, bytes(6), 0xAA, b"\xAA"),
        (0x02, bytes(3), 0xAA, b"\xAA"),
        (0x03, bytes(7), 0xAA, b"\xAA"),
        (0x01, bytes(7), 0xAA, bytes(2)),  # 无备用信道地址应为 1B
    ]
    for mt, ma, bt, ba in bad_cases:
        try:
            enc.build_set_channel(mt, ma, bt, ba)
            raise AssertionError(
                f"类型 0x{mt:02X}/地址 {len(ma)}B/备用 {len(ba)}B 应抛 EncodeError")
        except EncodeError:
            pass
    print("    A2H 信道地址长度校验 OK")


def main() -> int:
    print("=" * 60)
    print("SL427 参数设置 AFN=16H~20H 测试")
    print("=" * 60)
    tests = [
        ("16H", test_16h_recharge_alarm),
        ("17H", test_17h_level_limits),
        ("18H", test_18h_pressure_limits),
        ("19H/1AH", test_19h_water_quality),
        ("1BH", test_1bh_water_amount),
        ("1CH", test_1ch_relay_code_len),
        ("1DH", test_1dh_relay_addr),
        ("1EH", test_1eh_relay_auto_switch),
        ("1FH", test_1fh_flow_limits),
        ("20H", test_20h_report_threshold),
        ("10H 地址校验", test_10h_set_addr_validation),
        ("A2H 信道校验", test_a2h_channel_validation),
        ("校验", test_validation_errors),
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
    print("✅ 参数 AFN 测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
