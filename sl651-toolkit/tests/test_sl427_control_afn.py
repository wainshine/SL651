#!/usr/bin/env python3
"""SL427 控制命令/配置 AFN (90H~96H, A0H~A2H) 编码与响应解析测试。

规约依据：7.4.2~7.4.8、7.2.22~7.2.24 / 附录 B 表 B.78~B.91、B.28~B.31。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl427 import SL427Decoder, SL427Encoder, encode_address, make_ctrl
from sl427.encoder import EncodeError

FAILURES: list[str] = []


def _enc() -> SL427Encoder:
    return SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))


def _extract(frame: bytes, data_len: int) -> tuple[int, bytes]:
    """从命令帧提取 (AFN, 数据域 D)；这些 AFN 的 AUX = PW(2B)+Tp(7B)。"""
    L = frame[1]
    user = frame[3:3 + L]
    assert len(user) == 16 + data_len, f"L={L} 与数据域 {data_len}B 不符"
    return user[6], bytes(user[7:7 + data_len])


def _resp(afn: int, data: bytes) -> bytes:
    return _enc().build_frame(afn, make_ctrl(dir_=1, func_code=0), data)


def _decode(frame: bytes):
    r = SL427Decoder().decode(frame)
    assert r.crc_ok, f"CRC 应通过: {frame.hex().upper()}"
    return r


def test_90h_reset() -> None:
    enc = _enc()
    afn, data = _extract(enc.build_reset(), 1)
    assert afn == 0x90 and data == b"\x01", data.hex()
    _, data = _extract(enc.build_reset(factory_reset=True), 1)
    assert data == b"\x02", data.hex()
    r = _decode(_resp(0x90, b"\x5a"))
    e = [x for x in r.elements if x.name == "复位响应"]
    assert e and e[0].value == "执行完毕", e
    print("    90H 复位 OK")


def test_91h_clear_history() -> None:
    enc = _enc()
    afn, data = _extract(enc.build_clear_history(rain=True, water=True), 1)
    assert afn == 0x91 and data == b"\x05", data.hex()
    r = _decode(_resp(0x91, b"\x05"))
    e = [x for x in r.elements if x.name == "清空历史数据"]
    assert e and "雨量" in e[0].value and "水量" in e[0].value, e
    print("    91H 清空历史数据 OK")


def test_92h_93h_pump() -> None:
    enc = _enc()
    _, data = _extract(enc.build_start_pump(3), 1)
    assert data == b"\x03", data.hex()
    _, data = _extract(enc.build_start_pump(3, is_valve=True), 1)
    assert data == b"\xf3", data.hex()
    # 响应 D4~D7=1010B, D0~D3=编号
    r = _decode(_resp(0x92, b"\xa3"))
    e = [x for x in r.elements if x.name == "启动响应"]
    assert e and "水泵编号3" in e[0].value and "执行完毕" in e[0].value, e
    _, data = _extract(enc.build_stop_pump(15, is_valve=True), 1)
    assert data == b"\xff", data.hex()
    print("    92H/93H 启停水泵/阀门 OK")


def test_94h_95h_switch() -> None:
    enc = _enc()
    afn, data = _extract(enc.build_switch_comm("A"), 1)
    assert afn == 0x94 and data == b"\xa9", data.hex()
    _, data = _extract(enc.build_switch_relay_work("B"), 1)
    assert data == b"\xa6", data.hex()
    r = _decode(_resp(0x94, b"\xa9"))
    e = [x for x in r.elements if x.name == "切换响应"]
    assert e and e[0].value == "A机", e
    r = _decode(_resp(0x95, b"\xa6"))
    e = [x for x in r.elements if x.name == "切换响应"]
    assert e and e[0].value == "B机", e
    print("    94H/95H 切换通信机/工作机 OK")


def test_96h_change_password() -> None:
    enc = _enc()
    afn, data = _extract(enc.build_change_password(1234), 2)
    assert afn == 0x96 and data == bytes.fromhex("3412"), data.hex()
    r = _decode(_resp(0x96, bytes.fromhex("3412")))
    e = [x for x in r.elements if x.name == "密码设置响应"]
    assert e and e[0].value == 1234, e
    print("    96H 修改密码 OK")


def test_a0h_realtime_kinds() -> None:
    enc = _enc()
    mask = (1 << 1) | (1 << 9)  # 水位 + 水质
    afn, data = _extract(enc.build_set_realtime_kinds(mask), 2)
    assert afn == 0xA0 and data == mask.to_bytes(2, "little")
    r = _decode(_resp(0xA0, mask.to_bytes(2, "little")))
    e = [x for x in r.elements if x.name == "需查询的实时数据种类"]
    assert e and "水位" in e[0].value and "水质" in e[0].value, e
    print("    A0H 实时数据种类 OK")


def test_a1h_report_kinds() -> None:
    enc = _enc()
    mask = 1  # 雨量
    afn, data = _extract(enc.build_set_report_kinds(mask, [10, 60]), 2 + 4)
    assert afn == 0xA1
    assert data[:2] == b"\x01\x00", data.hex()
    assert data[2:4] == bytes.fromhex("1000"), data.hex()  # 10 -> LE BCD
    assert data[4:6] == bytes.fromhex("6000"), data.hex()  # 60 -> LE BCD
    r = _decode(_resp(0xA1, data))
    vals = {x.name: x.value for x in r.elements}
    assert "雨量" in vals.get("数据自报种类", ""), vals
    assert vals.get("自报间隔[雨量]") == 10, vals
    assert vals.get("自报间隔[水位]") == 60, vals
    print("    A1H 自报种类及间隔 OK")


def test_a2h_channel() -> None:
    enc = _enc()
    main_addr = bytes.fromhex("01020304050607")  # 7B
    afn, data = _extract(enc.build_set_channel(0x02, main_addr), 1 + 7 + 1 + 1)
    assert afn == 0xA2
    assert data[0] == 0x02 and data[1:8] == main_addr
    assert data[8] == 0xAA and data[9] == 0xAA  # 无备用信道
    r = _decode(_resp(0xA2, data))
    e = [x for x in r.elements if x.name == "主备信道配置"]
    assert e, r.elements
    print("    A2H 主备信道配置 OK")


def test_validation_errors() -> None:
    enc = _enc()
    bad = [
        lambda: enc.build_start_pump(16),
        lambda: enc.build_switch_comm("C"),
        lambda: enc.build_change_password(10000),
        lambda: enc.build_set_realtime_kinds(0x10000),
        lambda: enc.build_set_report_kinds(0, [0]),
        lambda: enc.build_set_report_kinds(0, [10000]),
        lambda: enc.build_set_report_kinds(0, [1] * 16),
    ]
    for i, fn in enumerate(bad):
        try:
            fn()
            raise AssertionError(f"第{i}个超限调用未抛 EncodeError")
        except EncodeError:
            pass
    print(f"    {len(bad)} 项超限校验 OK")


def test_control_fill_response_tolerance() -> None:
    """控制/配置响应的 0xAA 缺测填充不得抛 DecodeError（审计 v2.3 M-2）。"""
    for afn, data in [(0x96, b"\xAA" * 2), (0xA0, b"\xAA" * 2), (0xA1, b"\xAA" * 4)]:
        r = _decode(_resp(afn, data))
        assert r.elements, f"AFN 0x{afn:02X} 应产出降级要素"
    r = _decode(_resp(0x96, b"\xAA" * 2))
    assert r.elements[0].value == "-", r.elements
    print("    96H/A0H/A1H 0xAA 填充降级 OK")


def main() -> int:
    print("=" * 60)
    print("SL427 控制/配置 AFN 90H~96H, A0H~A2H 测试")
    print("=" * 60)
    tests = [
        ("90H", test_90h_reset),
        ("91H", test_91h_clear_history),
        ("92H/93H", test_92h_93h_pump),
        ("94H/95H", test_94h_95h_switch),
        ("96H", test_96h_change_password),
        ("A0H", test_a0h_realtime_kinds),
        ("A1H", test_a1h_report_kinds),
        ("A2H", test_a2h_channel),
        ("0xAA 填充容错", test_control_fill_response_tolerance),
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
    print("✅ 控制/配置 AFN 测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
