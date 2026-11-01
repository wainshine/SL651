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
