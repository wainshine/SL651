#!/usr/bin/env python3
"""SL427 分帧（DIV=1）重组测试（v1.4.0 审计 v2.6 M-1）。

覆盖：B0/84 重组、C0/83 安全降级、缺片、乱序、坏 CRC、单帧 DIVS=1、
编码侧 divs= 对称性。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl427 import SL427Decoder, SL427Encoder, encode_address, make_ctrl
from sl651.crc import crc8

FAILURES: list[str] = []


def _enc() -> SL427Encoder:
    return SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))


def _packet(enc: SL427Encoder, afn: int, data: bytes, divs: int,
            func_code: int = 0x0D) -> bytes:
    return enc.build_frame(
        afn, make_ctrl(dir_=1, func_code=func_code, div=1), data, divs=divs)


def _elements(msg) -> list[tuple]:
    return [(e.name, e.value, e.raw) for e in msg.elements]


def test_b0_two_frames_equal_single() -> None:
    enc = _enc()
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200")
    single = enc.build_frame(0xB0, make_ctrl(dir_=1, func_code=0x0D), payload)
    expected = _elements(SL427Decoder().decode(single))

    mid = len(payload) // 2
    d = SL427Decoder()
    out = d.feed(_packet(enc, 0xB0, payload[:mid], 2))
    out += d.feed(_packet(enc, 0xB0, payload[mid:], 1))
    assert len(out) == 1, f"应重组 1 帧, 实际 {len(out)}"
    msg = out[0]
    assert msg.reassembled and msg.packet_count == 2
    assert msg.crc_ok
    assert _elements(msg) == expected, "重组结果应与单帧逐字段一致"
    print("    B0 两帧重组 == 单帧 OK")


def test_b0_out_of_order() -> None:
    enc = _enc()
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200")
    d = SL427Decoder()
    assert d.feed(_packet(enc, 0xB0, payload[3:], 1)) == []
    out = d.feed(_packet(enc, 0xB0, payload[:3], 2))
    assert len(out) == 1 and out[0].reassembled
    print("    乱序 2/1 重组 OK")


def test_b0_missing_fragment_no_garbage() -> None:
    enc = _enc()
    d = SL427Decoder()
    out = d.feed(_packet(enc, 0xB0, b"\x60\x12\x01\x00", 2))
    assert out == [], "缺片不应产出任何报文"
    print("    缺片不产出垃圾 OK")


def test_b0_bad_crc_rejected() -> None:
    enc = _enc()
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200")
    p1 = bytearray(_packet(enc, 0xB0, payload[:3], 2))
    p1[11] ^= 0x01
    p2 = _packet(enc, 0xB0, payload[3:], 1)
    d = SL427Decoder()
    out = d.feed(bytes(p1)) + d.feed(p2)
    assert out == [], "坏 CRC 分片不得重组"
    assert d.errors and d.dropped_frames >= 1
    print("    坏 CRC 分片被拒 OK")


def test_84_two_frames() -> None:
    enc = _enc()
    # 12.34V -> 2B BCD 小端 34 12；拆成 1B+1B
    data = bytes.fromhex("3412")
    d = SL427Decoder()
    out = d.feed(_packet(enc, 0x84, data[:1], 2))
    out += d.feed(_packet(enc, 0x84, data[1:], 1))
    assert len(out) == 1 and out[0].reassembled
    values = [e.value for e in out[0].elements]
    assert "12.34" in values, values
    print("    84 两帧重组 OK")


def test_single_divs_one_in_feed_and_decode() -> None:
    enc = _enc()
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200")
    frame = _packet(enc, 0xB0, payload, 1)

    d = SL427Decoder(allow_single_div=True)
    out = d.feed(frame)
    assert len(out) == 1 and out[0].reassembled
    assert any("单帧" in w or "多帧" in w for w in out[0].warnings), out[0].warnings

    r = SL427Decoder().decode(frame)
    assert not r.elements and any("分帧" in w for w in r.warnings), r.warnings
    print("    单帧 DIVS=1：feed 解析 + decode 安全降级 OK")


def test_c0_and_83_div_safe_degrade() -> None:
    enc = _enc()
    # C0：可解析单帧但安全降级为空要素 + warning
    frame = _packet(enc, 0xC0, b"\x00" * 15, 2, func_code=0x02)
    d = SL427Decoder()
    out = d.feed(frame)
    assert len(out) == 1
    assert not out[0].elements, "C0 DIV 不得产出要素"
    assert any("分帧" in w for w in out[0].warnings)

    # 83：L×1K 语义未证，feed 直接安全丢弃并记 error
    frame83 = _packet(enc, 0x83, b"\x00" * 10, 2, func_code=0x02)
    d83 = SL427Decoder()
    assert d83.feed(frame83) == []
    assert d83.errors and "L×1K" in d83.errors[0]
    print("    C0/83 DIV 安全降级 OK")


def test_encoder_divs_symmetry() -> None:
    enc = _enc()
    payload = b"\x60\x12\x01\x00\x02\x00"
    frames = [
        _packet(enc, 0xB0, payload[:3], 2),
        _packet(enc, 0xB0, payload[3:], 1),
    ]
    # 编码帧应含 2B 控制域：C DIV=1 + DIVS
    assert frames[0][3] & 0x40 and frames[0][4] == 2
    assert frames[1][4] == 1
    try:
        enc.build_frame(0xB0, make_ctrl(dir_=1, func_code=0x0D), payload)
    except Exception:
        pass
    # 带 DIV 位但不给 divs 必须拒绝
    try:
        enc.build_frame(0xB0, make_ctrl(dir_=1, func_code=0x0D, div=1), payload)
        raise AssertionError("DIV=1 缺 divs 应抛 EncodeError")
    except Exception as e:
        from sl651.errors import EncodeError
        assert isinstance(e, EncodeError)
    print("    encoder divs 对称性 OK")


def test_b0_manual_frame() -> None:
    """按规约表3 手工拼 B0 分帧（不依赖项目 encoder），验证重组。"""
    addr = encode_address(1, 110108, 1284)
    ctrl1 = make_ctrl(dir_=1, func_code=0x0D)
    ctrl2 = make_ctrl(dir_=1, func_code=0x0D, div=1)
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200")

    def binary(ctrl: int, divs: int | None, data: bytes) -> bytes:
        user = bytes([ctrl]) + (bytes([divs]) if divs is not None else b"") + addr + bytes([0xB0]) + data
        return bytes([0x68, len(user), 0x68]) + user + bytes([crc8(user), 0x16])

    single = binary(ctrl1, None, payload)
    expected = _elements(SL427Decoder().decode(single))
    mid = len(payload) // 2
    f1 = binary(ctrl2, 2, payload[:mid])
    f2 = binary(ctrl2, 1, payload[mid:])
    d = SL427Decoder()
    out = d.feed(f1) + d.feed(f2)
    assert len(out) == 1 and out[0].reassembled and out[0].crc_ok
    assert _elements(out[0]) == expected
    print("    手工拼 B0 分帧重组 == 单帧 OK")


def test_b0_out_of_order_three() -> None:
    enc = _enc()
    payload = bytes.fromhex("6012") + bytes.fromhex("0100") + bytes.fromhex("0200") + b"\x03\x04\x05"
    third = len(payload) // 3
    parts = [payload[:third], payload[third:2 * third], payload[2 * third:]]
    frames = {
        3: _packet(enc, 0xB0, parts[0], 3),
        2: _packet(enc, 0xB0, parts[1], 2),
        1: _packet(enc, 0xB0, parts[2], 1),
    }
    d = SL427Decoder()
    out = d.feed(frames[1]) + d.feed(frames[3]) + d.feed(frames[2])
    assert len(out) == 1 and out[0].reassembled and out[0].packet_count == 3
    print("    3 帧乱序 1/3/2 重组 OK")


def test_pending_cap_and_ttl() -> None:
    enc = _enc()
    d = SL427Decoder()
    for i in range(120):
        e = SL427Encoder(encode_address(1, 110108, i + 1))
        d.feed(_packet(e, 0xB0, b"\x00" * 6, 2))
    assert len(d._pending) <= d._pending_max_groups, len(d._pending)

    d2 = SL427Decoder()
    d2.feed(_packet(enc, 0xB0, b"\x00" * 6, 2))
    for meta in d2._pending_meta.values():
        meta["updated"] -= d2._pending_ttl + 1
    d2.feed(b"")
    assert d2.errors and "超时" in d2.errors[0], d2.errors
    print(f"    分帧缓存上限 {len(d._pending)} 组 + TTL 淘汰 OK")


def test_large_div_direct_parse() -> None:
    """D 合计 300B >255：直接解析不再合成超限单帧。"""
    enc = _enc()
    payload = b"\x01" * 300
    f1 = _packet(enc, 0xB0, payload[:150], 2, func_code=0x01)
    f2 = _packet(enc, 0xB0, payload[150:], 1, func_code=0x01)
    d = SL427Decoder()
    out = d.feed(f1) + d.feed(f2)
    assert len(out) == 1, f"应重组 1 帧, errors={d.errors[:2]}"
    assert out[0].reassembled and out[0].packet_count == 2
    assert out[0].data_len == 300, out[0].data_len
    print("    300B 分片直接解析 OK")


def test_b1_solid_storage_parse() -> None:
    enc = _enc()
    data = (bytes([0x10]) + bytes.fromhex("12010122") + bytes.fromhex("12010122")
            + bytes.fromhex("001000"))
    r = SL427Decoder().decode(enc.build_frame(0xB1, make_ctrl(1, 0x01), data))
    names = [e.name for e in r.elements]
    assert "参数种类/编号" in names and "开始时间" in names and "结束时间" in names, names
    assert any(e.name == "雨量" for e in r.elements), names

    # L-1：多记录只解析首条必须留 warning
    multi = data[:9] + bytes.fromhex("001000") * 12
    rm = SL427Decoder().decode(enc.build_frame(0xB1, make_ctrl(1, 0x01), multi))
    assert any("仅解析首条" in w for w in rm.warnings), rm.warnings

    # L-2：BCD 合法但日历越界必须占位 + warning
    bad_time = bytes([0x01]) + bytes.fromhex("30240102") + bytes.fromhex("30240102")
    rt = SL427Decoder().decode(enc.build_frame(0xB1, make_ctrl(1, 0x01), bad_time))
    assert any(e.name == "开始时间" and e.value == "-" for e in rt.elements), rt.elements
    assert any("越界" in w for w in rt.warnings), rt.warnings
    print("    B1 固态存储头/数据 + 多记录/时间校验 OK")


def test_84_overlong_warning() -> None:
    enc = _enc()
    r = SL427Decoder().decode(enc.build_frame(0x84, make_ctrl(1, 0x0D),
                                               bytes.fromhex("3412FF")))
    assert any(">2B" in w for w in r.warnings), r.warnings
    assert any(e.name == "电压" and e.value == "12.34" for e in r.elements)
    print("    84 超长 warning OK")


def test_div_invalid_bcd_degrades() -> None:
    """M-2：DIV 重组直接解析遇非法 BCD 必须降级，不得裸抛 ValueError。"""
    enc = _enc()
    payload = bytes.fromhex(
        "dc17f01bf2e5dfb14175377d0f1c6724cd97c9154fe4808ba782cd892b67252ddd167b492382")
    n = len(payload)
    chunks = [payload[:n // 3], payload[n // 3:2 * n // 3], payload[2 * n // 3:]]
    d = SL427Decoder()
    out = []
    for i, chunk in enumerate(chunks):
        out += d.feed(_packet(enc, 0xB1, chunk, 3 - i, func_code=0x08))
    assert len(out) == 1, f"应重组 1 帧, errors={d.errors[:2]}"
    msg = out[0]
    assert any("解析失败" in w for w in msg.warnings), msg.warnings
    assert any(e.name == "重组原始数据" for e in msg.elements), msg.elements
    print("    DIV 非法 BCD 降级原始摘要 OK")


def main() -> int:
    print("=" * 60)
    print("SL427 分帧重组测试")
    print("=" * 60)
    tests = [
        ("B0 两帧==单帧", test_b0_two_frames_equal_single),
        ("B0 乱序", test_b0_out_of_order),
        ("B0 缺片", test_b0_missing_fragment_no_garbage),
        ("B0 坏 CRC", test_b0_bad_crc_rejected),
        ("84 两帧", test_84_two_frames),
        ("单帧 DIVS=1", test_single_divs_one_in_feed_and_decode),
        ("C0/83 安全降级", test_c0_and_83_div_safe_degrade),
        ("encoder divs", test_encoder_divs_symmetry),
        ("手工拼 B0", test_b0_manual_frame),
        ("3 帧乱序", test_b0_out_of_order_three),
        ("缓存上限/TTL", test_pending_cap_and_ttl),
        ("300B 直接解析", test_large_div_direct_parse),
        ("B1 解析", test_b1_solid_storage_parse),
        ("84 超长", test_84_overlong_warning),
        ("DIV 非法 BCD", test_div_invalid_bcd_degrades),
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
    print("✅ 分帧重组测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
