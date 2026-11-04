#!/usr/bin/env python3
"""SL651 表 C.1 / 表 G.1 常量基线测试（v1.4.2 WP-1）。

表 C.1 为规范性附录（ASCII 编码正文），表 G.1 为资料性附录（SL330 人工置数）。
本测试固化关键覆盖：HEX 键全集、ASCII 130 字面键、G 表独立、FD RAW 解析。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl651 import SL651Decoder, SL651Encoder
from sl651 import constants as C
from sl651.decoder import _ascii_time_step_desc

FAILURES: list[str] = []


def test_hex_table_coverage() -> None:
    print(">>> 表 C.1 HEX 覆盖")
    keys = set(C.SL651_ELEMENTS)
    expected = {f"{h:02x}" for h in range(0x01, 0x76)} | {f"f{h:x}" for h in range(0x0, 0xE)} | {"80"}
    # F0~FD 共 14 个；01~75 共 117；80 厂商自定义
    expected |= {"fd"}
    missing = expected - keys
    assert not missing, f"缺键: {sorted(missing)[:10]}"
    assert len(keys) == 132, f"应为 132 键（131 行 + 80H），实际 {len(keys)}"
    reserved = {f"{h:02x}" for h in range(0x76, 0xF0)} - {"80"}
    assert not (reserved & keys), "不应收录 76H~EFH 保留区（80H 厂商自定义除外）"
    # 58H~5FH 是 WP1~WP8
    for i, h in enumerate(range(0x58, 0x60), start=1):
        name, unit, _ = C.SL651_ELEMENTS[f"{h:02x}"]
        assert name == f"水压{i}" and unit == "kPa", (h, name, unit)
    for h in range(0x60, 0x68):
        assert C.SL651_ELEMENTS[f"{h:02x}"][1] == "m³"
    for h in range(0x68, 0x70):
        assert C.SL651_ELEMENTS[f"{h:02x}"][1] == "m³/h"
    for h in range(0x70, 0x73):
        assert C.SL651_ELEMENTS[f"{h:02x}"][0].startswith("交流") and C.SL651_ELEMENTS[f"{h:02x}"][1] == "V"
    for h in range(0x73, 0x76):
        assert C.SL651_ELEMENTS[f"{h:02x}"][0].startswith("交流") and C.SL651_ELEMENTS[f"{h:02x}"][1] == "A"
    assert C.SL651_ELEMENTS["fd"][2] == "RAW"
    print(f"    {len(keys)} 键；58H~75H + FDH 覆盖 OK")


def test_ascii_c1_table() -> None:
    print(">>> 表 C.1 ASCII 130 字面键")
    assert len(C.SL651_ASCII_ELEMENTS) == 130, len(C.SL651_ASCII_ELEMENTS)
    assert C.SL651_ASCII_ELEMENTS["NS"] == ("开机台数", "台")
    assert C.SL651_ASCII_ELEMENTS["SQ"] == ("含沙量", "kg/m³")
    assert C.SL651_ASCII_ELEMENTS["SW"] == ("输沙量", "万吨")
    assert C.SL651_ASCII_ELEMENTS["ZT"][0].startswith("遥测站状态")
    assert "SD" not in C.SL651_ASCII_ELEMENTS
    assert "MT" not in C.SL651_ASCII_ELEMENTS
    assert C.SL651_ASCII_ELEMENTS["WP1"] == ("水压1", "kPa")
    assert C.SL651_ASCII_ELEMENTS["WP3"] == ("水压3", "kPa")
    assert C.SL651_ASCII_ELEMENTS["SYL1"] == ("水表1剩余水量", "m³")
    assert C.SL651_ASCII_ELEMENTS["SBL1"] == ("水表1每小时水量", "m³/h")
    assert C.SL651_ASCII_ELEMENTS["VTA"] == ("交流A相电压", "V")
    assert C.SL651_ASCII_ELEMENTS["VIA"] == ("交流A相电流", "A")
    assert C.SL651_ASCII_ELEMENTS["DATA"][0] == "流速批量数据"
    assert "DRxnn" not in C.SL651_ASCII_ELEMENTS
    assert _ascii_time_step_desc("DRN05") is not None
    print("    NS/SQ/SW/ZT/SYL/SBL/WP/VTA/VIA/DATA + DRxnn 动态 OK")


def test_g_table_separate() -> None:
    print(">>> 表 G.1 独立")
    g = C.SL651_ASCII_ELEMENTS_G
    assert g["SD"] == ("日平均含沙量", "kg/m³")
    assert g["SDS"][0] == "日平均含沙量测算方式"
    assert g["SQS"][0] == "含沙量测算方式"
    assert g["SWD"] == ("日输沙总量", "万吨")
    assert "SD" not in C.SL651_ASCII_ELEMENTS
    assert "SQS" not in C.SL651_ASCII_ELEMENTS
    print(f"    G 表 {len(g)} 个核心码独立 OK")


def test_fd_raw_decode() -> None:
    print(">>> FDH RAW 解析")
    enc = SL651Encoder(center_addr=1, station_addr="1234567890",
                       password=0, station_type=0x48)
    body = (bytes([0xF1, 0xF1]) + enc.station_addr_bytes
            + bytes([0x4B, 0xF0, 0xF0]) + bytes.fromhex("2601010100")
            + bytes([0xFD, 0x18]) + bytes.fromhex("010203"))
    r = SL651Decoder().decode(enc.build_frame(0x32, body))
    fd = [e for e in r.elements if e.code == "FD"]
    assert fd and "流速批量数据" in fd[0].value, [(e.code, e.value) for e in r.elements]
    print("    FDH 不数值化、显示字节摘要 OK")


def test_fixture_c1_full() -> None:
    """131 行 TSV 基线：guide/ASCII/名称/单位逐行回归（名称/单位为工具显示口径；映射/单位经 PDF 表 C.1 核对）。"""
    import csv
    fixture = Path(__file__).resolve().parent / "fixtures" / "sl651_table_c1.tsv"
    rows = list(csv.DictReader(fixture.open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 131, len(rows)
    for row in rows:
        guide = row["guide"]
        assert guide in C.SL651_ELEMENTS, f"缺 guide {guide}"
        name, unit, _ = C.SL651_ELEMENTS[guide]
        assert (name, unit) == (row["hex_name"], row["hex_unit"]), (guide, name, unit, row)
        code = row["ascii"]
        if code == "DRxnn":
            assert "DRxnn" not in C.SL651_ASCII_ELEMENTS
            continue
        assert code in C.SL651_ASCII_ELEMENTS, f"缺 ASCII {code} ({guide})"
        aname, aunit = C.SL651_ASCII_ELEMENTS[code]
        assert (aname, aunit) == (row["ascii_name"], row["ascii_unit"]), (code, aname, aunit, row)
    assert "pH" in C.SL651_ASCII_ELEMENTS and "PH" not in C.SL651_ASCII_ELEMENTS
    print(f"    {len(rows)} 行 TSV 逐行一致；pH 大小写 OK")


def test_ascii_lookup_invariant() -> None:
    """每个 ASCII 表键都必须能穿过运行时 lookup（pH/PH/ph 大小写无关）。"""
    from sl651.decoder import _lookup_ascii
    for key, expected in C.SL651_ASCII_ELEMENTS.items():
        assert _lookup_ascii(key) == expected, key
        assert _lookup_ascii(key.upper()) == expected, key.upper()
        assert _lookup_ascii(key.lower()) == expected, key.lower()
    assert _lookup_ascii("pH") == ("pH", "")
    assert _lookup_ascii("PH") == ("pH", "")
    assert _lookup_ascii("ph") == ("pH", "")
    print(f"    {len(C.SL651_ASCII_ELEMENTS)} 个表键的 lookup 不变量 OK")


def main() -> int:
    print("=" * 60)
    print("表 C.1 / 表 G.1 常量基线测试")
    print("=" * 60)
    for fn in (test_hex_table_coverage, test_ascii_c1_table,
               test_fixture_c1_full, test_ascii_lookup_invariant,
               test_g_table_separate, test_fd_raw_decode):
        try:
            fn()
        except Exception as e:
            print(f"    ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            FAILURES.append(f"{fn.__name__}: {e}")
    print()
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("✅ 常量基线测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
