#!/usr/bin/env python3
"""SL651 多包 (SYN/ETB) 跨帧重组测试（C3）。

规约依据：6.3.2.5（ETB=后续还有包，ETX=最后一包）、表22（HEX/BCD SYN 帧：
SYN 后 3 字节，高 12 位包总数 / 低 12 位序列号，范围 1~4095）。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl651 import SL651Decoder, SL651Encoder, crc16
from sl651 import constants as C

FAILURES: list[str] = []


def _make_packet(orig: bytes, part: bytes, total: int, seq: int,
                 end_marker: int) -> bytes:
    """基于正常帧头构造一个 SYN 分包帧。"""
    header = bytearray(orig[2:13])  # center(1)+station(5)+pwd(2)+func(1)+ident(2)
    body_len = 3 + len(part)       # SYN 后至结束符前字节数（含 3B 包头）
    ident_hi = (header[9] & 0x80) | ((body_len >> 8) & 0x0F)
    header[9] = ident_hi
    header[10] = body_len & 0xFF
    pkt = ((total << 12) | seq).to_bytes(3, "big")
    frame = bytes([0x7E, 0x7E]) + bytes(header) + bytes([C.SYN]) + pkt + \
        part + bytes([end_marker])
    crc = crc16(frame)
    return frame + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def _orig_frame() -> bytes:
    enc = SL651Encoder(center_addr=0x01, station_addr="1234567890",
                       password=0, station_type=0x48)
    elements = [
        (0x39, 12.345, 4, 3),
        (0x38, 12.60, 2, 2),
        (0x20, 5.5, 3, 1),
        (0x1F, 88.8, 3, 1),
    ]
    return enc.build_timing_frame(elements, obs_time=datetime(2026, 9, 14, 10, 0))


def _split(orig: bytes) -> tuple[bytes, bytes]:
    body_len = ((orig[11] & 0x0F) << 8) | orig[12]
    body = orig[C.BODY_OFFSET:C.BODY_OFFSET + body_len]
    mid = len(body) // 2
    return body[:mid], body[mid:]


def _ascii_orig_frame() -> bytes:
    enc = SL651Encoder(center_addr=0x01, station_addr="1234567890",
                       password=0, station_type=0x48)
    return enc.build_ascii_frame(
        [("Z", "12.345"), ("Q", "5.678")],
        obs_time=datetime(2026, 9, 14, 10, 0))


def _make_ascii_packet(orig: bytes, part: bytes, total: int, seq: int,
                       end_marker: int) -> bytes:
    """基于正常 ASCII 帧头构造 ASCII SYN 分包帧（6 位包总数/序列号）。"""
    ident_raw = int(orig[19:23].decode("ascii"), 16)
    body_len = 6 + len(part)  # 包总数(3)+序列号(3) + 载荷
    ident_hi = ((ident_raw >> 8) & 0x80) | ((body_len >> 8) & 0x0F)
    ident_lo = body_len & 0xFF
    hdr = bytearray(orig[:19])
    hdr.extend(f"{ident_hi:02X}{ident_lo:02X}".encode("ascii"))
    pkt = f"{total:03d}{seq:03d}".encode("ascii")
    frame = bytes(hdr) + bytes([C.SYN]) + pkt + part + bytes([end_marker])
    crc = crc16(frame)
    return frame + f"{crc:04X}".encode("ascii")


def test_ascii_reassemble_direction_preserved() -> None:
    """ASCII 多包重组后方向位（ident bit7）不得丢失（审计 v2.3 L-2）。"""
    orig = _ascii_orig_frame()
    ident_raw = int(orig[19:23].decode("ascii"), 16) | 0x8000  # 置方向=下行
    body_len = ((ident_raw >> 8) & 0x0F) << 8 | (ident_raw & 0xFF)
    etx_pos = C.ASCII_BODY_OFFSET + body_len
    head = bytearray(orig[:19]) + f"{ident_raw:04X}".encode("ascii")
    head += bytes([orig[C.ASCII_STX_OFFSET]])
    frame_no_crc = bytes(head) + orig[C.ASCII_BODY_OFFSET:etx_pos + 1]
    orig = frame_no_crc + f"{crc16(frame_no_crc):04X}".encode("ascii")

    body = orig[C.ASCII_BODY_OFFSET:C.ASCII_BODY_OFFSET + body_len]
    mid = len(body) // 2
    p1 = _make_ascii_packet(orig, body[:mid], 2, 1, C.ETB)
    p2 = _make_ascii_packet(orig, body[mid:], 2, 2, C.ETX)

    dec = SL651Decoder()
    assert dec.feed(p1) == [], "首包应等待后续包"
    out = dec.feed(p2)
    assert len(out) == 1, f"应重组出 1 帧, 实际 {len(out)}"
    r = out[0]
    assert r.crc_ok and r.encoding == "ASCII", f"crc={r.crc_ok} enc={r.encoding}"
    assert r.direction == 1, f"方向位丢失: direction={r.direction}"
    assert r.function_code == 0x32
    print("    ASCII 多包重组方向位保留 OK")


def test_reassemble_two_packets() -> None:
    orig = _orig_frame()
    p1_body, p2_body = _split(orig)
    p1 = _make_packet(orig, p1_body, 2, 1, C.ETB)
    p2 = _make_packet(orig, p2_body, 2, 2, C.ETX)

    dec = SL651Decoder()
    assert dec.feed(p1) == [], "首包应等待后续包"
    out = dec.feed(p2)
    assert len(out) == 1, f"应重组出 1 帧, 实际 {len(out)}"
    r = out[0]
    assert r.crc_ok and r.function_code == 0x32, f"crc={r.crc_ok} func=0x{r.function_code:02X}"
    codes = [e.code for e in r.elements]
    assert codes == ["39", "38", "20", "1F"], codes
    wl = [e for e in r.elements if e.code == "39"][0]
    assert abs(float(wl.value) - 12.345) < 0.001, wl.value
    print(f"    2 包重组 OK, {len(r.elements)} 要素")


def test_reassemble_out_of_order() -> None:
    orig = _orig_frame()
    b1, b2 = _split(orig)
    p1 = _make_packet(orig, b1, 2, 1, C.ETB)
    p2 = _make_packet(orig, b2, 2, 2, C.ETX)
    dec = SL651Decoder()
    assert dec.feed(p2) == []
    out = dec.feed(p1)
    assert len(out) == 1 and out[0].crc_ok
    assert [e.code for e in out[0].elements] == ["39", "38", "20", "1F"]
    print("    乱序到达重组 OK")


def test_reassemble_three_packets_single_call() -> None:
    orig = _orig_frame()
    body_len = ((orig[11] & 0x0F) << 8) | orig[12]
    body = orig[C.BODY_OFFSET:C.BODY_OFFSET + body_len]
    third = len(body) // 3
    parts = [body[:third], body[third:2 * third], body[2 * third:]]
    packets = []
    for i, part in enumerate(parts, start=1):
        end = C.ETX if i == 3 else C.ETB
        packets.append(_make_packet(orig, part, 3, i, end))
    dec = SL651Decoder()
    out = dec.feed(b"".join(packets))
    assert len(out) == 1 and out[0].crc_ok
    assert [e.code for e in out[0].elements] == ["39", "38", "20", "1F"]
    print("    3 包一次性重组 OK")


def test_reassemble_incremental_bytes() -> None:
    orig = _orig_frame()
    b1, b2 = _split(orig)
    p1 = _make_packet(orig, b1, 2, 1, C.ETB)
    p2 = _make_packet(orig, b2, 2, 2, C.ETX)
    stream = b"\x00\x11" + p1 + p2 + b"\xff"  # 前后含垃圾字节
    dec = SL651Decoder()
    out: list = []
    for i in range(0, len(stream), 3):
        out.extend(dec.feed(stream[i:i + 3]))
    assert len(out) == 1 and out[0].crc_ok, f"分片喂入应重组成功, 得到 {len(out)} 帧"
    assert [e.code for e in out[0].elements] == ["39", "38", "20", "1F"]
    print("    逐段喂入 + 垃圾字节 OK")


def test_single_frame_feed_passthrough() -> None:
    orig = _orig_frame()
    dec = SL651Decoder()
    out = dec.feed(orig)
    assert len(out) == 1 and out[0].function_code == 0x32
    # 两帧连续
    dec2 = SL651Decoder()
    out2 = dec2.feed(orig + orig)
    assert len(out2) == 2
    print("    单帧/多帧直通 OK")


def main() -> int:
    print("=" * 60)
    print("SL651 多包 SYN/ETB 重组测试")
    print("=" * 60)
    tests = [
        ("2 包重组", test_reassemble_two_packets),
        ("乱序重组", test_reassemble_out_of_order),
        ("3 包一次性", test_reassemble_three_packets_single_call),
        ("增量字节喂入", test_reassemble_incremental_bytes),
        ("单帧直通", test_single_frame_feed_passthrough),
        ("ASCII 方向位", test_ascii_reassemble_direction_preserved),
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
    print("✅ 多包重组测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
