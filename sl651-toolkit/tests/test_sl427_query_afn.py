#!/usr/bin/env python3
"""SL427 查询类 AFN (50H~65H) 查询帧构造 + 响应帧解析测试。

规约依据：7.3.2~7.3.21 / 附录 B 表 B.32~B.71。
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


def _resp(afn: int, data: bytes) -> bytes:
    """构造查询响应帧（上行，无 AUX）。"""
    return _enc().build_frame(afn, make_ctrl(dir_=1, func_code=0), data)


def _decode(frame: bytes):
    r = SL427Decoder().decode(frame)
    assert r.crc_ok, f"CRC 应通过: {frame.hex().upper()}"
    return r


def test_query_frames_structure() -> None:
    enc = _enc()
    queries = [
        (enc.build_query_addr(), 0x50),
        (enc.build_query_clock(), 0x51),
        (enc.build_query_work_mode(), 0x52),
        (enc.build_query_report_kinds(), 0x53),
        (enc.build_query_realtime_kinds(), 0x54),
        (enc.build_query_recharge(), 0x55),
        (enc.build_query_remaining_alarm(), 0x56),
        (enc.build_query_event_record(), 0x5D),
        (enc.build_query_status_alarm(), 0x5E),
        (enc.build_query_pump_data(), 0x5F),
        (enc.build_query_relay_code_len(), 0x60),
        (enc.build_query_image(3), 0x61),
        (enc.build_query_relay_addr(), 0x62),
        (enc.build_query_relay_status(), 0x63),
        (enc.build_query_flow_limits(), 0x64),
        (enc.build_query_channel(), 0x65),
        (enc.build_query_history_daily(), 0x5C),
    ]
    for frame, afn in queries:
        r = _decode(frame)
        assert r.afn == afn, f"AFN 应为 0x{afn:02X}, 实际 0x{r.afn:02X}"
        # 查询帧无 AUX：L = C(1)+A(5)+AFN(1) [+data]
        extra = 1 if afn == 0x61 else 0
        assert frame[1] == 7 + extra, f"L={frame[1]} 应为 {7 + extra}"
    print(f"    {len(queries)} 个查询帧结构 OK")


def test_50h_addr_response() -> None:
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    r = _decode(_resp(0x50, addr))
    e = [x for x in r.elements if x.name == "站点地址"]
    assert e and "110108" in e[0].value and "1284" in e[0].value, e
    print("    50H 地址响应 OK")


def test_51h_clock_response() -> None:
    # 秒分时日月年 BCD: 30 15 14 12 05 26 -> 2026-05-12 14:15:30
    data = bytes.fromhex("301514120526")
    r = _decode(_resp(0x51, data))
    e = [x for x in r.elements if x.name == "站点时钟"]
    assert e and "2026-05-12 14:15:30" in e[0].value, e
    print("    51H 时钟响应 OK")


def test_52h_work_mode_response() -> None:
    r = _decode(_resp(0x52, bytes([1])))
    e = [x for x in r.elements if x.name == "工作模式"]
    assert e and e[0].value == "自报", e
    print("    52H 工作模式响应 OK")


def test_54h_realtime_kinds_response() -> None:
    mask = (1 << 0) | (1 << 2)  # bit0 确认/应答, bit2 水位
    r = _decode(_resp(0x54, mask.to_bytes(2, "little")))
    e = [x for x in r.elements if x.name == "实时数据种类"]
    assert e and "水位" in e[0].value, e
    print("    54H 实时数据种类响应 OK")


def test_55h_recharge_remaining_response() -> None:
    recharge = bytes.fromhex("34120000")  # 1234 的 4B 小端 BCD
    remaining = bytes.fromhex("7856000080")  # 5678 且末字节 D7=1(负)
    r = _decode(_resp(0x55, recharge + remaining))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("最近充值量") == 1234, vals
    assert vals.get("剩余水量") == -5678, vals
    print("    55H 充值量/剩余水量响应 OK")


def test_56h_remaining_alarm_response() -> None:
    alarm = bytes.fromhex("563412")   # 123456 LE BCD
    remaining = bytes.fromhex("7856000000")  # 5678 正
    r = _decode(_resp(0x56, alarm + remaining))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("剩余水量报警值") == 123456, vals
    assert vals.get("剩余水量") == 5678, vals
    print("    56H 剩余水量/报警值响应 OK")


def test_5eh_status_alarm_response() -> None:
    # 报警 LE: 0x0005 -> bit0 停电, bit2 报警; 终端状态 0x0001 -> 工作模式 自报确认
    r = _decode(_resp(0x5E, bytes.fromhex("0500") + bytes.fromhex("0100")))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("工作交流电停电告警") == "停电", vals
    assert vals.get("水位超限报警") == "报警", vals
    assert vals.get("终端工作模式") == "自报确认", vals
    print("    5EH 状态/报警响应 OK")


def test_5fh_pump_response() -> None:
    data = (220).to_bytes(2, "little") + (221).to_bytes(2, "little") + \
           (222).to_bytes(2, "little") + (10).to_bytes(2, "little") + \
           (11).to_bytes(2, "little") + (12).to_bytes(2, "little")
    r = _decode(_resp(0x5F, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("A相电压") == 220 and vals.get("C相电流") == 12, vals
    print("    5FH 水泵电机数据响应 OK")


def test_60h_relay_code_len_response() -> None:
    r = _decode(_resp(0x60, bytes([120])))
    e = [x for x in r.elements if x.name == "中继引导码长值"]
    assert e and e[0].value == 120, e
    print("    60H 中继引导码长值响应 OK")


def test_62h_relay_addr_response() -> None:
    a = encode_address(method=1, admin_code=110108, stn_id=1284)
    b = encode_address(method=2, hex_code="12345678")
    r = _decode(_resp(0x62, a + b))
    addrs = [x for x in r.elements if x.name.startswith("转发站地址")]
    assert len(addrs) == 2 and "1284" in addrs[0].value and "12345678" in addrs[1].value, addrs
    print("    62H 中继转发地址响应 OK")


def test_53h_report_kinds_response() -> None:
    mask = 1  # 雨量
    data = mask.to_bytes(2, "little") + bytes.fromhex("1000") + bytes.fromhex("6000")
    r = _decode(_resp(0x53, data))
    vals = {x.name: x.value for x in r.elements}
    assert "雨量" in vals.get("数据自报种类", ""), vals
    assert vals.get("自报间隔[雨量]") == 10, vals
    assert vals.get("自报间隔[水位]") == 60, vals
    print("    53H 自报种类及间隔响应 OK")


def test_5dh_event_record_response() -> None:
    counters = [(3).to_bytes(2, "little"), (5).to_bytes(2, "little")]
    data = b"".join(counters) + bytes(2 * 16)  # 18 项 × 2B
    r = _decode(_resp(0x5D, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("事件记录[数据初始化记录]") == 3, vals
    assert vals.get("事件记录[参数变更记录]") == 5, vals
    print("    5DH 事件记录响应 OK")


def test_57h_level_limits_response() -> None:
    body = bytes.fromhex("500500") + bytes.fromhex("1000") + bytes.fromhex("9999")
    data = body + bytes(4)
    r = _decode(_resp(0x57, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("水位基值[1]") == 5.5, vals
    assert vals.get("水位下限[1]") == 0.1, vals
    assert vals.get("水位上限[1]") == 99.99, vals
    # 负基值符号位
    neg = bytes([0x50, 0x05, 0x80]) + bytes.fromhex("0000") + bytes.fromhex("0000") + bytes(4)
    r2 = _decode(_resp(0x57, neg))
    v2 = {x.name: x.value for x in r2.elements}
    assert v2.get("水位基值[1]") == -5.5, v2
    print("    57H 水位基值/上下限响应 OK")


def test_58h_pressure_limits_response() -> None:
    data = bytes.fromhex("50000100") + bytes.fromhex("00000000") + bytes(4)
    r = _decode(_resp(0x58, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("水压上限[1]") == 100.5, vals
    assert vals.get("水压下限[1]") == 0.0, vals
    print("    58H 水压上/下限响应 OK")


def test_59h_water_quality_response() -> None:
    mask = (1 << 0) | (1 << 2)  # 水温 + 溶解氧
    data = mask.to_bytes(5, "little") + bytes.fromhex("34120000") + bytes.fromhex("78560000")
    r = _decode(_resp(0x59, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("水温") == 1234, vals
    assert vals.get("溶解氧") == 5678, vals
    # 下限 AFN=5AH
    r2 = _decode(_resp(0x5A, data))
    assert {x.name: x.value for x in r2.elements}.get("水温") == 1234
    print("    59H/5AH 水质参数响应 OK")


def test_63h_relay_status_response() -> None:
    record = bytes.fromhex("3014120526")  # 分30 时14 日12 星期月05 年26
    data = bytes([0x00, 0x0D]) + record  # b2: bit0 A机正常, bit2 值班A机, bit3 允许转发
    r = _decode(_resp(0x63, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("中继状态[工作机A机]") == "正常", vals
    assert vals.get("中继状态[值班机]") == "A机", vals
    assert vals.get("中继状态[转发]") == "允许", vals
    assert vals.get("切换记录[1]") == "2026-05-12 14:30", vals
    print("    63H 中继状态/切换记录响应 OK")


def test_64h_flow_limits_response() -> None:
    flow = bytes.fromhex("5634120000")  # 123.456 m³/s
    tail = bytes.fromhex("00000000")    # alarm + state
    r = _decode(_resp(0x64, flow + tail))
    e = [x for x in r.elements if x.name == "流量上限[1]"]
    assert e and abs(e[0].value - 123.456) < 0.001 and e[0].unit == "m³/s", e
    print("    64H 流量参数上限响应 OK")


def test_65h_channel_response() -> None:
    data = bytes([0x02]) + bytes.fromhex("01020304050607") + bytes([0xAA, 0xAA])
    r = _decode(_resp(0x65, data))
    vals = {x.name: x.value for x in r.elements}
    assert vals.get("主信道") == "IPV4 01020304050607", vals
    assert vals.get("备用信道") == "无", vals
    print("    65H 主备信道响应 OK")


def test_query_image_validation() -> None:
    enc = _enc()
    try:
        enc.build_query_image(256)
        raise AssertionError("图片编号超限应抛 EncodeError")
    except EncodeError:
        pass
    print("    图片编号校验 OK")


def test_fill_response_tolerance() -> None:
    """规约合法 0xAA/0xFF 缺测填充不得抛 DecodeError（审计 v2.3 M-2）。"""
    cases = [
        (0x50, b"\xAA" * 5),
        (0x53, b"\xAA" * 4),
        (0x55, b"\xAA" * 9),
        (0x56, b"\xAA" * 8),
        (0x57, b"\xAA" * 11),
        (0x58, b"\xAA" * 12),
        (0x59, b"\xAA" * 13),
        (0x5A, b"\xAA" * 13),
        (0x62, b"\xAA" * 5),
        (0x64, b"\xAA" * 9),
    ]
    for afn, data in cases:
        r = _decode(_resp(afn, data))  # 不抛异常即通过
        assert r.elements, f"AFN 0x{afn:02X} 应产出降级要素"
    r = _decode(_resp(0x50, b"\xFF" * 5))
    assert r.elements and r.elements[0].value == "-", r.elements
    r = _decode(_resp(0x55, b"\xAA" * 9))
    assert all(x.value == "-" for x in r.elements), r.elements
    print(f"    {len(cases)} 个 0xAA 填充 + 0xFF 填充降级 OK")


def main() -> int:
    print("=" * 60)
    print("SL427 查询类 AFN 50H~65H 测试")
    print("=" * 60)
    tests = [
        ("查询帧结构", test_query_frames_structure),
        ("50H", test_50h_addr_response),
        ("51H", test_51h_clock_response),
        ("52H", test_52h_work_mode_response),
        ("54H", test_54h_realtime_kinds_response),
        ("55H", test_55h_recharge_remaining_response),
        ("56H", test_56h_remaining_alarm_response),
        ("5EH", test_5eh_status_alarm_response),
        ("5FH", test_5fh_pump_response),
        ("60H", test_60h_relay_code_len_response),
        ("62H", test_62h_relay_addr_response),
        ("53H", test_53h_report_kinds_response),
        ("5DH", test_5dh_event_record_response),
        ("57H", test_57h_level_limits_response),
        ("58H", test_58h_pressure_limits_response),
        ("59H/5AH", test_59h_water_quality_response),
        ("63H", test_63h_relay_status_response),
        ("64H", test_64h_flow_limits_response),
        ("65H", test_65h_channel_response),
        ("校验", test_query_image_validation),
        ("0xAA 填充容错", test_fill_response_tolerance),
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
    print("✅ 查询类 AFN 测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
