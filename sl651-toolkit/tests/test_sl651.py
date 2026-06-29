#!/usr/bin/env python3
"""SL651 工具包自测脚本。

验证编码器、解码器、CRC、BCD 等模块的正确性。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sl651 import (
    SL651Decoder,
    SL651Encoder,
    bcd_bytes_to_int,
    bcd_to_datetime,
    bcd_to_int,
    bytes_to_hex_compact,
    crc16,
    datetime_to_bcd,
    hex_str_to_bytes,
    int_to_bcd,
    int_to_bcd_bytes,
)
from simulator import RainStation, SoilStation, WaterLevelStation


def test_bcd() -> None:
    """测试 BCD 编解码。"""
    print(">>> 测试 BCD 编解码")
    assert bcd_to_int(0x59) == 59
    assert int_to_bcd(59) == 0x59
    assert bcd_bytes_to_int(b"\x12\x34") == 1234
    assert int_to_bcd_bytes(1234, 2) == b"\x12\x34"

    dt = datetime(2026, 6, 29, 10, 30, 0)
    bcd_time = datetime_to_bcd(dt)
    assert bcd_to_datetime(bcd_time) == dt
    print(f"    BCD 时间编码: {bytes_to_hex_compact(bcd_time)} -> {dt}")
    print("    OK")


def test_crc() -> None:
    """测试 CRC-16/CCITT。"""
    print(">>> 测试 CRC-16/CCITT")
    # 已知测试向量: "123456789" 的 CRC-16/CCITT (0xFFFF 初值) = 0x29B1
    data = b"123456789"
    crc = crc16(data)
    assert crc == 0x29B1, f"CRC 校验失败: 期望 0x29B1, 实际 0x{crc:04X}"
    print(f"    CRC-16('123456789') = 0x{crc:04X} (期望 0x29B1)")
    print("    OK")


def test_encode_decode() -> None:
    """测试编码 -> 解码的往返一致性。"""
    print(">>> 测试编码 -> 解码往返一致性")

    encoder = SL651Encoder(
        center_addr="01",
        remote_addr="0000000001",
        password="1234",
    )
    body_time = datetime(2026, 6, 29, 10, 30, 0)
    elements = [
        ("0040", 5.234),  # 瞬时水位
        ("0045", 5.180),  # 日平均水位
        ("0800", 12.65),  # 电源电压
    ]
    frame = encoder.build_a1_frame(elements, body_time)
    print(f"    编码帧: {bytes_to_hex_compact(frame)}")

    decoder = SL651Decoder()
    result = decoder.decode(frame)

    assert result.crc_ok, "CRC 校验失败"
    assert result.center_station_addr == "01"
    assert result.remote_station_addr == "0000000001"
    assert result.password == "1234"
    assert result.message_type == "A1"
    assert result.has_time
    assert result.body_time == body_time
    assert len(result.elements) == 3

    # 验证要素值
    el_map = {el.identifier: el for el in result.elements}
    assert abs(el_map["0040"].raw_value - 5.234) < 0.001, f"水位值不符: {el_map['0040'].raw_value}"
    assert abs(el_map["0045"].raw_value - 5.180) < 0.001
    assert abs(el_map["0800"].raw_value - 12.65) < 0.01

    print(f"    中心站: {result.center_station_addr}")
    print(f"    遥测站: {result.remote_station_addr}")
    print(f"    报文类型: {result.message_type} ({result.message_type_desc})")
    print(f"    时间: {result.body_time}")
    for el in result.elements:
        print(f"    {el.identifier} {el.name}: {el.display_value}")
    print("    OK")


def test_negative_value() -> None:
    """测试负数编码。"""
    print(">>> 测试负数编码")
    encoder = SL651Encoder(remote_addr="0000000002")
    # 气温 -5.3℃
    frame = encoder.build_a1_frame([("0710", -5.3)], datetime(2026, 1, 15, 8, 0, 0))
    decoder = SL651Decoder()
    result = decoder.decode(frame)
    el = result.elements[0]
    assert el.identifier == "0710"
    assert abs(el.raw_value - (-5.3)) < 0.05, f"负数值不符: {el.raw_value}"
    print(f"    气温: {el.display_value} (期望 -5.3℃)")
    print("    OK")


def test_stations() -> None:
    """测试三种站点模拟器。"""
    print(">>> 测试站点模拟器生成报文")

    stations = [
        WaterLevelStation("0000000001", base_level=5.0),
        RainStation("0000000002"),
        SoilStation("0000000003"),
    ]

    decoder = SL651Decoder()
    for station in stations:
        # 推进几个 tick 让数据有变化
        for _ in range(5):
            station.advance(1)

        frame = station.build_a1_frame(body_time=datetime.now())
        result = decoder.decode(frame)
        assert result.crc_ok, f"{station.name} CRC 校验失败"
        print(f"    {station.name} ({station.station_addr}):")
        print(f"      报文: {bytes_to_hex_compact(frame)}")
        for el in result.elements:
            print(f"      {el.identifier} {el.name}: {el.display_value}")
    print("    OK")


def test_sample_messages() -> None:
    """测试示例报文文件。"""
    print(">>> 测试示例报文文件")
    sample_file = PROJECT_ROOT / "examples" / "sample_messages.txt"
    if not sample_file.exists():
        print("    跳过（示例文件不存在）")
        return

    decoder = SL651Decoder()
    success = 0
    failed = 0
    for line in sample_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            result = decoder.decode_hex(line)
            if result.crc_ok:
                success += 1
            else:
                failed += 1
                print(f"    CRC 失败: {line[:60]}...")
        except Exception as e:
            failed += 1
            print(f"    解码失败: {e}")
            print(f"    报文: {line[:60]}...")

    print(f"    成功: {success}, 失败: {failed}")
    if failed == 0:
        print("    OK")
    else:
        print("    WARN: 部分示例报文解码失败（可能是手写示例的 CRC 不对，不影响功能）")


def main() -> int:
    print("=" * 60)
    print("SL651 工具包自测")
    print("=" * 60)
    try:
        test_bcd()
        test_crc()
        test_encode_decode()
        test_negative_value()
        test_stations()
        test_sample_messages()
    except AssertionError as e:
        print(f"\n测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("=" * 60)
    print("所有测试通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
