#!/usr/bin/env python3
"""v1.5.0 规约符合性测试套件（期望值只来自规约表/福建示例）。

覆盖 v3.0 审计的 M-1~M-5、L-1/L-2、v2.9 L-1（静默截断）与 I-1（A1H 长度提示）。
与既有回归套件的区别：这里的期望值从 SL427-2021 表33~44/表18/表54、
SL651-2014 表C.1/D.1/D.4 与《福建省水文监测数据接入规定》示例逐字推导，
不来自当前实现的输出。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sl651 import SL651Decoder, SL651Encoder
from sl651 import constants as SC
from sl651.crc import crc16
from sl651.errors import EncodeError
from sl427 import SL427Decoder, SL427Encoder, encode_address
from sl427 import constants as C
from sl427.constants import make_ctrl

FAILURES: list[str] = []


def _enc427() -> SL427Encoder:
    return SL427Encoder(encode_address(1, 110000, 1))


def _dec427() -> SL427Decoder:
    return SL427Decoder()


def _b0(func: int, data: bytes, alarm: int = 0, state: int = 0) -> bytes:
    return _enc427().build_query_response(func, data, alarm, state)


def _names(elements):
    return [e.name for e in elements]


# ----------------------------------------------------------------------
# M-1 / L-2：SL427 类型表与实时值
# ----------------------------------------------------------------------

def test_sl427_type_table_spec() -> None:
    """表33~44：13 个标量/结构类型码的 byteLen/decimal/unit 与规约一致。

    0x00（确认/应答）、0x0D（电压/报警状态）、0x0E（综合参数/统计雨量）
    为上下文相关类型，不在本表内。
    """
    expected = {
        0x01: (3, 1, "mm"), 0x02: (4, 3, "m"), 0x03: (5, 3, "m³/s"),
        0x04: (3, 3, "m/s"), 0x05: (3, 2, "m"), 0x06: (3, 0, "kW"),
        0x07: (8, 0, ""), 0x08: (4, 2, "kW·h"), 0x09: (2, 1, "℃"),
        0x0A: (4, 0, ""), 0x0B: (4, 0, "%"), 0x0C: (3, 1, "mm"),
        0x0F: (4, 2, "kPa"),
    }
    for func, (n, d, unit) in expected.items():
        spec = C.CTRL_FUNC_MAP[func]
        assert (spec["byteLen"], spec["decimal"], spec["unit"]) == (n, d, unit), \
            (hex(func), spec, (n, d, unit))
    print("    16 类型码 byteLen/decimal/unit OK")


def test_sl427_type_values() -> None:
    """逐类型构造合规数据，断言名称/数值/单位。"""
    dec = _dec427()

    def one(func, data):
        r = dec.decode(_b0(func, data))
        return [(e.name, e.value, e.unit) for e in r.elements
                if e.name not in ("观测时间",) and "告警" not in e.name
                and e.name not in ("终端工作模式", "IC卡功能有效", "定值控制投入",
                                   "水泵工作状态", "终端箱门状态", "电源工作状态")]

    # 水温 2B：个位/十分位=0x23，十位=0x01 → 12.3℃
    assert one(0x09, bytes.fromhex("2301"))[0] == ("水温", "12.3", "℃")
    # 水压 4B：123456 → 1234.56 kPa
    assert one(0x0F, bytes.fromhex("56341200"))[0] == ("水压", "1234.56", "kPa")
    # 蒸发量 3B：1234 → 123.4mm
    assert one(0x0C, bytes.fromhex("341200"))[0] == ("蒸发量", "123.4", "mm")
    # 电量 4B：123456 → 1234.56 kW·h
    assert one(0x08, bytes.fromhex("56341200"))[0] == ("电量参数", "1234.56", "kW·h")
    # 气象 8B：气压1000hPa / 风速12.34 / 风向0 / 气温-12.3℃
    weather = [(e.name, e.value, e.unit) for e in dec.decode(_b0(0x07, bytes.fromhex("00100034210023F1"))).elements
               if e.name in ("气压", "风速", "风向", "气温")]
    assert weather == [("气压", "1000", "hPa"), ("风速", "12.34", "m/s"),
                       ("风向", "0", ""), ("气温", "-12.3", "℃")], weather
    # 土壤 4B：含水率25.3% + 深度20cm
    soil = [(e.name, e.value, e.unit) for e in dec.decode(_b0(0x0B, bytes.fromhex("53022000"))).elements
            if e.name in ("土壤含水率", "采集深度")]
    assert soil == [("土壤含水率", 25.3, "%"), ("采集深度", 20, "cm")], soil
    # 流量对：12.345 m³/s + 累计水量 1234 m³
    flow = [(e.name, e.value, e.unit) for e in dec.decode(_b0(0x03, bytes.fromhex("4523010000") + bytes.fromhex("3412000000"))).elements
            if e.name in ("流量", "累计水量")]
    assert flow == [("流量", "12.345", "m³/s"), ("累计水量", "1234", "m³")], flow
    # 水质：水温 123.4℃ + 溶解氧 56.78mg/L
    quality = [(e.name, e.value, e.unit) for e in dec.decode(_b0(
        0x0A, ((1 << 0) | (1 << 2)).to_bytes(5, "little")
        + bytes.fromhex("34120000") + bytes.fromhex("78560000"))).elements
        if e.name in ("水温", "溶解氧")]
    assert quality == [("水温", "123.4", "℃"), ("溶解氧", "56.78", "mg/L")], quality

    # 综合参数：0x03 流量对 / 0x0A 水质 / 0x0B 土壤（每型一块）
    r = dec.decode(_b0(0x0E, bytes([1 << 5]) + bytes.fromhex("4523010000")
                       + bytes.fromhex("3412000000")))
    assert [e.name for e in r.elements if e.name in ("流量", "累计水量")] == \
        ["流量", "累计水量"], r.elements
    r = dec.decode(_b0(0x0E, bytes([1 << 0])
                       + (1 << 0).to_bytes(5, "little")
                       + bytes.fromhex("34120000")))
    assert [e.value for e in r.elements if e.name == "水温"] == ["123.4"], r.elements
    r = dec.decode(_b0(0x0E, bytes([1 << 1]) + bytes.fromhex("53022000")))
    assert [e.name for e in r.elements if e.name in ("土壤含水率", "采集深度")] == \
        ["土壤含水率", "采集深度"], r.elements
    print("    水温/水压/蒸发/电量/气象/土壤/流量对/水质/综合参数 OK")


def test_sl427_statistical_rain_spec() -> None:
    """表54 位域 + 表33 0.1mm：四类统计雨量 12.3mm。"""
    enc = _enc427()
    dec = _dec427()
    cases = {
        0x00: "时段降雨量(0min)",   # 0 个 5min 时段
        0x41: "小时降雨量(1h)",
        0x81: "日降雨量(1d)",
        0xC0: "测试/累计雨量",
    }
    for rtype, label in cases.items():
        frame = enc.build_self_report_c0(
            0x0E, bytes([rtype]) + bytes.fromhex("230100"),
            tp=datetime(2026, 7, 1, 6, 0))
        r = dec.decode(frame)
        got = [(e.name, e.value) for e in r.elements if "雨量" in e.name]
        assert got == [(f"统计雨量({label})", "12.3")], (hex(rtype), got)
    print("    统计雨量 4 类型 / 12.3mm OK")


def test_sl427_b1_spec() -> None:
    """B1 固态存储：0x09/0x0B/0x0A 按各自记录长度展开。"""
    enc = _enc427()
    dec = _dec427()
    head = bytes.fromhex("8000010125" "08010125")  # 参数0x80 + 2025-01-01 00:00~08:00

    # 0x09 水温：3×2B
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x09),
                                   head + bytes.fromhex("2301" * 3)))
    vals = [e for e in r.elements if e.name == "水温"]
    assert len(vals) == 3 and all(e.value == "12.3" for e in vals), vals
    # 0x0B 土壤：2×4B → 每记录 2 个要素
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x0B),
                                   bytes.fromhex("a000010125" "08010125")
                                   + bytes.fromhex("53022000" * 2)))
    vals = [e for e in r.elements if e.name in ("土壤含水率", "采集深度")]
    assert len(vals) == 4, vals
    # 0x0A 水质：B1 单参数 0x90 → 水温，2×4B
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x0A),
                                   bytes.fromhex("9000010125" "08010125")
                                   + bytes.fromhex("34120000" * 2)))
    vals = [e for e in r.elements if e.name == "水温"]
    assert len(vals) == 2 and all(e.value == "123.4" for e in vals), vals
    # 0x0A 的另一种 B1 形态：5B 位图 + 4B
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x0A),
                                   bytes.fromhex("9000010125" "08010125")
                                   + (1 << 0).to_bytes(5, "little")
                                   + bytes.fromhex("34120000")))
    assert [e.value for e in r.elements if e.name == "水温"] == ["123.4"], r.elements
    # 0x07 气象：2×8B → 每记录 4 个值
    weather = (bytes.fromhex("00100034210023F1")) * 2
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x07),
                                   bytes.fromhex("6000010125" "08010125") + weather))
    assert len([e for e in r.elements if e.name in ("气压", "风速", "风向", "气温")]) == 8
    # 0x03 流量对：2×10B
    pairs = (bytes.fromhex("4523010000") + bytes.fromhex("3412000000")) * 2
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x03),
                                   bytes.fromhex("2000010125" "08010125") + pairs))
    assert len([e for e in r.elements if e.name in ("流量", "累计水量")]) == 4
    print("    B1 0x09/0x0B/0x0A/0x07/0x03 记录展开 OK")


def test_sl427_water_quality_59_5a() -> None:
    """表18：59H/5AH 水质值按各自小数位/单位。"""
    enc = _enc427()
    dec = _dec427()
    data = ((1 << 0) | (1 << 2)).to_bytes(5, "little") \
        + bytes.fromhex("34120000") + bytes.fromhex("78560000")
    for afn in (0x59, 0x5A):
        r = dec.decode(enc.build_frame(afn, make_ctrl(1, 0x00), data))
        vals = {e.name: (e.value, e.unit) for e in r.elements}
        assert vals["水温"] == ("123.4", "℃"), vals
        assert vals["溶解氧"] == ("56.78", "mg/L"), vals
    print("    59H/5AH 水质小数位/单位 OK")


# ----------------------------------------------------------------------
# v2.9 L-1：不得静默丢弃
# ----------------------------------------------------------------------

def test_sl427_no_silent_drop() -> None:
    """B0 非数组多记录 / AFN=64 尾随 / B1 尾随 均须 warning。"""
    enc = _enc427()
    dec = _dec427()

    # B0/0x01：两条雨量 + 4B 状态 → 只解析首条，剩余 3B 须 warning
    data = bytes.fromhex("001000") + bytes.fromhex("002000") + b"\x00" * 4
    r = dec.decode(enc.build_frame(0xB0, make_ctrl(1, 0x01), data))
    assert len([e for e in r.elements if e.name == "雨量"]) == 1
    assert any("剩余 3B" in w for w in r.warnings), r.warnings

    # AFN=64：body 5B + 尾随 2B（先去掉 4B 状态）
    data = bytes.fromhex("4523010000") + b"\x00" * 4 + bytes.fromhex("ABCD")
    r = dec.decode(enc.build_frame(0x64, make_ctrl(1, 0x00), data))
    assert any("剩余 2B" in w for w in r.warnings), r.warnings

    # B1：3B 记录 + 1B 尾随
    head = bytes.fromhex("8000010125" "08010125")
    r = dec.decode(enc.build_frame(0xB1, make_ctrl(1, 0x09),
                                   head + bytes.fromhex("2301") + b"\xFF"))
    assert any("剩余 1B" in w for w in r.warnings), r.warnings

    # A1H：6B（2B 位图 + 2 个间隔）→ 规约 30B 提示
    r = dec.decode(enc.build_frame(0xA1, make_ctrl(1, 0x00),
                                   bytes.fromhex("0100" "1000" "6000")))
    assert any("30B" in w for w in r.warnings), r.warnings

    # 固定长度查询响应：5FH 应为 12B
    r = dec.decode(enc.build_frame(0x5F, make_ctrl(1, 0x00), b"\x00" * 10))
    assert any("固定 12B" in w for w in r.warnings), r.warnings

    # 综合参数水质块仅 4B：无法判定参数种类，降级原始 4B + warning
    r = dec.decode(enc.build_query_response(
        0x0E, bytes.fromhex("01") + bytes.fromhex("34120000")))
    assert any(e.name == "水质(原始4B)" for e in r.elements), r.elements
    assert any("水质块仅 4B" in w for w in r.warnings), r.warnings
    print("    B0/AFN64/B1/A1H/5FH/综合参数4B warning OK")


# ----------------------------------------------------------------------
# M-2 统计雨量已在 test_sl427_statistical_rain_spec
# M-3/M-5：SL651 F2/F3/FD
# ----------------------------------------------------------------------

def _sl651_enc() -> SL651Encoder:
    return SL651Encoder(center_addr=1, station_addr="1000000006", station_type=0x48)


def test_sl651_f2_spec() -> None:
    """表C.1 注 c：F2 固定定义符 F2H + 载荷；福建 0x35 样本逐字节。"""
    enc = _sl651_enc()
    payload = bytes.fromhex("5120312E323334")  # SL330 "Q 1.234"
    frame = enc.build_manual_frame(payload)
    assert frame[22:-3] == b"\xF2\xF2" + payload, frame[22:-3].hex()
    r = SL651Decoder().decode(frame)
    assert r.elements[0].raw == payload.hex().upper(), r.elements[0].raw

    fujian = bytes.fromhex(
        "7E7E0110000000060000350011022F7D221205102729F2F25120312E32333403BF56")
    rf = SL651Decoder().decode(fujian)
    assert rf.elements[0].raw == "5120312E323334", rf.elements[0].raw
    print("    F2/F2 定义符 + 福建 0x35 载荷 OK")


def test_sl651_f3_fd_spec() -> None:
    """表C.1 注 d/f：F3/FD 固定定义符，标识符之后全部为载荷。"""
    enc = _sl651_enc()
    hdr = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes + bytes([0x48, 0xF0, 0xF0])
           + bytes.fromhex("2601010100"))
    payload = bytes(range(40))

    r = SL651Decoder().decode(enc.build_frame(0x32, hdr + bytes([0xF3, 0xF3]) + payload))
    f3 = [e for e in r.elements if e.code == "F3"]
    assert len(f3) == 1 and f3[0].byte_len == 40, f3
    assert len(r.elements) == 1, r.elements

    r = SL651Decoder().decode(enc.build_frame(0x32, hdr + bytes([0xFD, 0xF6]) + payload))
    fd = [e for e in r.elements if e.code == "FD"]
    assert len(fd) == 1 and fd[0].byte_len == 40, fd
    assert len(r.elements) == 1, r.elements
    # FD FD 兼容口径：接受但必须留 warning（规约注 f 固定 F6H）
    r = SL651Decoder().decode(enc.build_frame(0x32, hdr + bytes([0xFD, 0xFD]) + payload))
    assert any("F6H" in w for w in r.warnings), r.warnings
    print("    F3/FD 固定定义符 + 消费到末尾 + FD FD warning OK")


def test_sl651_f3_real_reassembly() -> None:
    """真实福建 0x36 图片帧正文拆 2 个 SYN 包重组：仅 1 个 F3、载荷 243B。"""
    sample = ROOT / "examples" / "fujian_messages.txt"
    line = [l.strip() for l in sample.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
            and l.startswith("7E7E011000000006000036")][0]
    orig = bytes.fromhex(line)
    hdr_base = bytearray(orig[:13])
    body = orig[17:14 + ((orig[11] << 8) | orig[12])]
    mid = len(body) // 2
    frames = []
    for i, ch in enumerate([body[:mid], body[mid:]], 1):
        blen = 3 + len(ch)
        hdr = bytearray(hdr_base)
        hdr[11], hdr[12] = (blen >> 8) & 0xFF, blen & 0xFF
        pkt = bytes([0x00, 0x20, i])
        frame = bytearray(hdr) + bytes([SC.SYN]) + pkt + ch \
            + bytes([SC.ETB if i < 2 else SC.ETX])
        frame += crc16(bytes(frame)).to_bytes(2, "big")
        frames.append(bytes(frame))
    dec = SL651Decoder()
    out = []
    for f in frames:
        out += dec.feed(f)
    assert len(out) == 1 and out[0].reassembled
    els = out[0].elements
    assert len(els) == 1 and els[0].code == "F3" and els[0].byte_len == 220, els
    print("    真实 0x36 两包重组：1×F3/220B OK")


# ----------------------------------------------------------------------
# M-4 / L-1：SL651 标识符
# ----------------------------------------------------------------------

def test_sl651_downlink_ids_spec() -> None:
    """47H/48H/49H/3AH/41H/43H 正文与福建示例逐字节一致。"""
    enc = _sl651_enc()
    assert enc.build_init_solid_storage()[22:-3] == bytes.fromhex("9700")
    assert enc.build_reset_frame()[22:-3] == bytes.fromhex("9800")
    assert enc.build_change_password_frame(0, 0x4D2)[22:-3] == \
        bytes.fromhex("03100000031004D2")
    assert enc.build_query_body([0x26]) == bytes.fromhex("2619")
    assert enc.build_query_body([0x05]) == bytes.fromhex("0510")
    assert enc.build_read_config_frame([1, 2, 3])[22:-3] == \
        bytes.fromhex("012002280310")
    assert enc.build_read_config_frame([0x20, 0x23], function_code=0x43)[22:-3] == \
        bytes.fromhex("20082310")
    assert enc.build_read_config_frame([0x0D])[22:-3] == bytes.fromhex("0D40")
    assert enc.build_read_config_frame([0x97], function_code=0x43)[22:-3] == \
        bytes.fromhex("9700")
    # 未知/变长参数必须显式报错，不能静默 0 定义符
    for bad in (lambda: enc.build_query_body([0xF2]),
                lambda: enc.build_read_config_frame([0x04])):
        try:
            bad()
            raise AssertionError("未知/变长标识符未抛 EncodeError")
        except EncodeError:
            pass
    # 显式元组覆盖
    assert enc.build_query_body([(0x26, 3, 1)]) == bytes.fromhex("2619")
    print("    47/48/49/3A/41/43 正文 + 未知抛错 OK")


def test_sl651_downlink_namespace() -> None:
    """下行 41H 不得再解成附录C 要素；49H 上下行均显示密码。"""
    enc = _sl651_enc()
    dec = SL651Decoder()
    f41 = ("7E7E" "1000000006" "00" "0000" "41" "800E" "02" "0000"
           "221206135846" "012002280310" "05" "0EE7")
    r = dec.decode_hex(f41)
    names = _names(r.elements)
    assert "断面面积" not in names, names
    assert [e.code for e in r.elements] == ["01", "02", "03"], names
    assert names[0] == "中心站地址(4B)", names

    f49 = ("7E7E" "0000000001" "00" "0000" "49" "8010" "02" "0000"
           "221206161203" "03100000" "031004D2" "05" "0ADF")
    vals = {e.name: e.value for e in dec.decode_hex(f49).elements}
    assert vals == {"旧密码": "0x0000", "新密码": "0x04D2"}, vals

    f49up = ("7E7E0000000000010000490013020002221206161150F1F1"
             "0000000001031004D2030573")
    vals = {e.name: e.value for e in dec.decode_hex(f49up).elements}
    assert vals == {"新密码": "0x04D2"}, vals

    # 非标 49H 定义符：降级原始摘要 + warning，不按固定步长盲切
    f49bad = ("7E7E" "0000000001" "00" "0000" "49" "8010" "02" "0000"
              "221206161203" "03100000" "031104D2" "05" "0ADF")
    rbad = dec.decode_hex(f49bad)
    assert any("03 10H" in w for w in rbad.warnings), rbad.warnings

    # 40H 数据不足声明长度：留 warning，不静默错位
    f40short = enc.build_frame(0x40, bytes.fromhex("0310AA"), direction=1,
                               end_marker=SC.ENQ)
    r40 = dec.decode(f40short)
    assert any("数据不足" in w for w in r40.warnings), r40.warnings

    # 49H 正文非 8B 整数倍：尾部留 warning
    f49tail = enc.build_frame(0x49, bytes.fromhex("03100000031004D2FF"),
                              direction=1, end_marker=SC.ENQ)
    r49t = dec.decode(f49tail)
    assert any("8B 整数倍" in w for w in r49t.warnings), r49t.warnings
    print("    41H 命名空间 / 49H 密码/非标定义符 / 40H 短数据 / 49H 尾随 OK")


# ----------------------------------------------------------------------


def test_sl427_a1h_30b() -> None:
    """A1H 固定 30B 口径（2B 位图 + 14×2B）可编码且解码无长度 warning。"""
    enc = _enc427()
    dec = _dec427()
    frame = enc.build_set_report_kinds_30(0x0003, [10] * 14)
    data = frame[10:-11]  # D 域（去掉 C/A/AFN 与 PW+Tp+CS+END）
    assert len(data) == 30, len(data)
    assert data[:2] == b"\x03\x00"
    # 用同一 30B 数据构造上行响应，验证解码不再报“非 30B”
    up = enc.build_frame(0xA1, make_ctrl(1, 0x00), data)
    r = dec.decode(up)
    assert any(e.name == "自报间隔[雨量]" for e in r.elements), r.elements
    assert not any("30B" in w for w in r.warnings), r.warnings
    try:
        enc.build_set_report_kinds_30(0x0003, [10] * 13)
        raise AssertionError("13 个间隔未抛 EncodeError")
    except EncodeError:
        pass
    print("    A1H 固定 30B 编码/解码 OK")


def main() -> int:
    tests = [
        ("SL427 类型表", test_sl427_type_table_spec),
        ("SL427 类型值", test_sl427_type_values),
        ("SL427 统计雨量", test_sl427_statistical_rain_spec),
        ("SL427 B1 记录", test_sl427_b1_spec),
        ("SL427 59H/5AH 水质", test_sl427_water_quality_59_5a),
        ("SL427 不静默丢弃", test_sl427_no_silent_drop),
        ("SL427 A1H 30B", test_sl427_a1h_30b),
        ("SL651 F2 定义符", test_sl651_f2_spec),
        ("SL651 F3/FD 固定定义符", test_sl651_f3_fd_spec),
        ("SL651 0x36 真实重组", test_sl651_f3_real_reassembly),
        ("SL651 下行标识符", test_sl651_downlink_ids_spec),
        ("SL651 下行命名空间", test_sl651_downlink_namespace),
    ]
    for name, fn in tests:
        print(f">>> {name}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
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
    print("✅ 规约符合性套件全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
