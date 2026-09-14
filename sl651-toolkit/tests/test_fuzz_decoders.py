#!/usr/bin/env python3
"""解码器健壮性（变异/模糊）测试。

对合法报文做截断、字节翻转、插入、删除、随机噪声等变异，
断言解码器只抛受控的 DecodeError，绝不泄漏 IndexError/AttributeError/
UnicodeDecodeError 等未处理异常，也不挂起。
"""

from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl651 import SL651Decoder
from sl651.decoder import DecodeError as SL651DecodeError
from sl651.encoder import SL651Encoder
from sl427 import SL427Decoder, SL427Encoder, encode_address
from sl427.decoder import DecodeError as SL427DecodeError

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = (SL651DecodeError, SL427DecodeError)
FAILURES: list[str] = []


def _base_sl651_frames() -> list[bytes]:
    frames = []
    sample = ROOT / "examples" / "fujian_messages.txt"
    if sample.exists():
        for line in sample.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                frames.append(bytes.fromhex(line))
            if len(frames) >= 8:
                break
    enc = SL651Encoder(center_addr=1, station_addr="1234567890", station_type=0x48)
    frames.append(enc.build_timing_frame([(0x39, 12.345, 4, 3)],
                                         obs_time=datetime(2026, 9, 14, 10, 0)))
    frames.append(enc.build_ascii_frame([("Z", "12.345")]))
    return frames


def _base_sl427_frames() -> list[bytes]:
    enc = SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))
    return [
        enc.build_heartbeat(),
        enc.build_self_report_c0(func_code=0x02,
                                 data=bytes.fromhex("45230100")),
        enc.build_self_report_84(12.3),
        enc.build_set_clock(datetime(2026, 9, 14, 10, 0)),
    ]


def _mutate(data: bytes, rng: random.Random) -> bytes:
    kind = rng.randrange(5)
    if not data:
        return bytes([rng.randrange(256)])
    if kind == 0:  # 截断
        return data[: rng.randrange(len(data) + 1)]
    if kind == 1:  # 单字节翻转
        b = bytearray(data)
        i = rng.randrange(len(b))
        b[i] ^= 1 << rng.randrange(8)
        return bytes(b)
    if kind == 2:  # 插入随机字节
        b = bytearray(data)
        b.insert(rng.randrange(len(b) + 1), rng.randrange(256))
        return bytes(b)
    if kind == 3:  # 删除字节
        b = bytearray(data)
        del b[rng.randrange(len(b))]
        return bytes(b)
    # 随机噪声
    return bytes(rng.randrange(256) for _ in range(rng.randrange(0, 64)))


def _exercise(decoder, frame: bytes, tag: str) -> None:
    for label, call in (
        ("decode(bytes)", lambda: decoder.decode(frame)),
        ("decode_hex(str)", lambda: decoder.decode_hex(frame.hex().upper())),
    ):
        try:
            call()
        except ALLOWED:
            pass
        except Exception as e:  # noqa: BLE001
            FAILURES.append(f"{tag} {label}: {type(e).__name__}: {e}")


def test_sl651_fuzz() -> None:
    print(">>> SL651 解码器变异测试")
    rng = random.Random(20260914)
    bases = _base_sl651_frames()
    decoder = SL651Decoder()
    # 基线自检
    for f in bases:
        r = decoder.decode(f)
        assert isinstance(r.crc_ok, bool)
    for i in range(600):
        base = bases[rng.randrange(len(bases))]
        _exercise(decoder, _mutate(base, rng), f"SL651#{i}")
    assert not FAILURES, f"SL651 未受控异常: {FAILURES[:5]}"
    print(f"    600 次变异无未受控异常 OK")


def test_sl427_fuzz() -> None:
    print(">>> SL427 解码器变异测试")
    rng = random.Random(4272026)
    bases = _base_sl427_frames()
    decoder = SL427Decoder()
    for f in bases:
        r = decoder.decode(f)
        assert isinstance(r.crc_ok, bool)
    for i in range(600):
        base = bases[rng.randrange(len(bases))]
        _exercise(decoder, _mutate(base, rng), f"SL427#{i}")
    assert not FAILURES, f"SL427 未受控异常: {FAILURES[:5]}"
    print(f"    600 次变异无未受控异常 OK")


def test_sl651_feed_fuzz() -> None:
    """流式 feed() 对随机/变异输入不抛未受控异常。"""
    print(">>> SL651 feed() 流式健壮性")
    rng = random.Random(5142026)
    bases = _base_sl651_frames()
    for _ in range(300):
        dec = SL651Decoder()
        payload = b"".join(
            _mutate(bases[rng.randrange(len(bases))], rng) for _ in range(rng.randrange(1, 4))
        )
        try:
            dec.feed(payload)
        except ALLOWED:
            pass
        except Exception as e:  # noqa: BLE001
            FAILURES.append(f"feed: {type(e).__name__}: {e}")
    assert not FAILURES, f"feed 未受控异常: {FAILURES[:5]}"
    print("    300 次流式喂入无未受控异常 OK")


def test_legal_frames_no_raise() -> None:
    """合法帧（含 0xAA/0xFF 缺测填充）不得抛异常，且填充须降级为 '-'。

    审计 v2.4 L-4：变异测试只断言「仅抛受控 DecodeError」，无法发现
    「合法输入被拒」或「合法填充被解释为错误值」。本用例补正向断言。
    """
    from sl427 import make_ctrl
    print(">>> 合法帧正向断言（不得抛异常）")
    dec651 = SL651Decoder()
    for f in _base_sl651_frames():
        dec651.decode(f)  # 不抛异常即通过

    dec427 = SL427Decoder()
    for f in _base_sl427_frames():
        dec427.decode(f)

    enc = SL427Encoder(encode_address(method=1, admin_code=110108, stn_id=1284))
    fill_afns = [0x50, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
                 0x5A, 0x5D, 0x5E, 0x5F, 0x60, 0x62, 0x63, 0x64, 0x84, 0x96]
    for afn in fill_afns:
        n = 2 if afn in (0x52, 0x60, 0x84, 0x96) else (4 if afn in (0x53, 0x54, 0x5E, 0x5D) else 9)
        frame = enc.build_frame(afn, make_ctrl(dir_=1, func_code=0), b"\xAA" * n)
        r = dec427.decode(frame)  # 合法填充不得抛异常
        vals = [e.value for e in r.elements]
        assert vals, f"AFN 0x{afn:02X} 填充应产出降级要素"
        assert all(v == "-" for v in vals), \
            f"AFN 0x{afn:02X} 填充应降级为 '-', 实际 {vals[:4]}"
    print(f"    {len(_base_sl651_frames())} SL651 + {len(_base_sl427_frames())} SL427 合法帧 + "
          f"{len(fill_afns)} 个填充响应 OK")


def main() -> int:
    print("=" * 60)
    print("解码器变异/模糊测试")
    print("=" * 60)
    for name, fn in (("SL651", test_sl651_fuzz), ("SL427", test_sl427_fuzz),
                     ("SL651 feed", test_sl651_feed_fuzz),
                     ("合法帧正向", test_legal_frames_no_raise)):
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
        for f in FAILURES[:20]:
            print(f"  - {f}")
        return 1
    print("✅ 变异测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
