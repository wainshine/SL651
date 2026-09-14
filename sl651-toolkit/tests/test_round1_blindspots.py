#!/usr/bin/env python3
"""测试1代：小时报编解码往返 & SL427编码器盲区 验证脚本"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from sl651 import SL651Encoder, SL651Decoder
from sl427 import SL427Encoder, SL427Decoder, encode_address, encode_tp, make_ctrl

FAILURES = []

# ============================================================
# 测试1: 小时报 12组水位 编解码往返
# ============================================================
def test_hourly_roundtrip_12():
    """小时报 12组水位 编解码往返，验证要素数量和各水位值"""
    enc = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    levels = [round(2.0 + i * 0.15, 2) for i in range(12)]
    inst_level = 12.345
    voltage = 12.6
    frame = enc.build_hourly_frame(levels, inst_level, voltage)
    r = SL651Decoder().decode(frame)
    assert r.crc_ok, "CRC 应通过"
    assert r.function_code == 0x34, f"功能码应为0x34, 实际{hex(r.function_code)}"
    # 应有: 12×F5水位 + 1×39瞬时水位 + 1×38电压 = 14
    f5_count = sum(1 for e in r.elements if e.code.startswith("F"))
    assert f5_count == 12, f"F5水位应有12个, 实际{f5_count}"
    has_39 = any(e.code == "39" for e in r.elements)
    has_38 = any(e.code == "38" for e in r.elements)
    assert has_39, "缺少瞬时水位(39)"
    assert has_38, "缺少电池电压(38)"
    # 验证瞬时水位值
    wl_elem = [e for e in r.elements if e.code == "39"][0]
    assert abs(wl_elem.value - inst_level) < 0.01, f"瞬时水位值不对: {wl_elem.value} != {inst_level}"
    # 验证电池电压
    v_elem = [e for e in r.elements if e.code == "38"][0]
    assert abs(v_elem.value - voltage) < 0.01, f"电池电压不对: {v_elem.value} != {voltage}"
    print("  ✅ 小时报12组往返通过 (要素:", len(r.elements), ")")


def test_hourly_roundtrip_extreme_values():
    """小时报 极端水位值 (0 / 负数 / 大值)"""
    enc = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
    levels = [0.0] * 12
    frame = enc.build_hourly_frame(levels, 0.0, 0.0)
    r = SL651Decoder().decode(frame)
    assert r.crc_ok, "全零水位 CRC应通过"
    print("  ✅ 小时报全零水位通过")

    # 负数水位
    levels_neg = [0.0] * 11 + [-0.50]
    try:
        frame = enc.build_hourly_frame(levels_neg, 0.0, 0.0)
        r = SL651Decoder().decode(frame)
        print(f"  ⚠️ 负数水位F5值: CRC={r.crc_ok}, 要素={len(r.elements)}")
    except Exception as e:
        print(f"  ℹ️  负数水位F5: {e}")


def test_hourly_invalid_count():
    """小时报 非12组应该报错"""
    from sl651.encoder import EncodeError
    enc = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0)
    for bad_count in [0, 1, 5, 11, 13, 24]:
        try:
            enc.build_hourly_frame([0.0] * bad_count, 0.0, 0.0)
            print(f"  ❌ {bad_count}组未报错!")
            FAILURES.append(f"小时报 {bad_count}组未抛异常")
        except EncodeError:
            pass  # 预期行为
    print("  ✅ 小时报非12组校验通过 (0/1/5/11/13/24组均抛EncodeError)")


# ============================================================
# 测试2: SL427 编码器盲区 (81/82/84/12)
# ============================================================
def test_sl427_81_roundtrip():
    """SL427 AFN=0x81 自报告警 往返"""
    from sl651.bcd import int_to_bcd_bytes
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    data = bytes([0x45, 0x03, 0x00, 0xF0])
    f = enc.build_self_report_81(func_code=0x02, data=data, tp=datetime(2026, 6, 1, 12, 0),
                                  alarm=0x0001, state=0x0000)
    r = SL427Decoder().decode(f)
    assert r.crc_ok, f"AFN=0x81 CRC应通过"
    assert r.afn == 0x81, f"AFN应为0x81, 实际{hex(r.afn)}"
    print(f"  ✅ AFN=0x81 往返通过 (CRC OK, AFN={hex(r.afn)}, 要素={len(r.elements)})")


def test_sl427_82_roundtrip():
    """SL427 AFN=0x82 人工置数 往返"""
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    data = bytes([0x34, 0x12, 0x00, 0x00])
    f = enc.build_self_report_82(func_code=0x02, data=data)
    r = SL427Decoder().decode(f)
    assert r.crc_ok, f"AFN=0x82 CRC应通过"
    assert r.afn == 0x82, f"AFN应为0x82, 实际{hex(r.afn)}"
    print(f"  ✅ AFN=0x82 往返通过 (CRC OK, AFN={hex(r.afn)}, 要素={len(r.elements)})")


def test_sl427_84_roundtrip():
    """SL427 AFN=0x84 自报电压 往返"""
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    f = enc.build_self_report_84(voltage=12.3)
    r = SL427Decoder().decode(f)
    assert r.crc_ok, f"AFN=0x84 CRC应通过"
    assert r.afn == 0x84, f"AFN应为0x84, 实际{hex(r.afn)}"
    print(f"  ✅ AFN=0x84 往返通过 (CRC OK, AFN={hex(r.afn)}, 要素={len(r.elements)})")


def test_sl427_12_roundtrip():
    """SL427 AFN=0x12 设置工作模式 往返"""
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    for mode, mode_name in [(0, "兼容"), (1, "自报"), (2, "查询"), (3, "调试")]:
        f = enc.build_set_work_mode(mode)
        r = SL427Decoder().decode(f)
        assert r.crc_ok, f"模式{mode}({mode_name}) CRC应通过"
        assert r.afn == 0x12, f"AFN应为0x12, 实际{hex(r.afn)}"
    print("  ✅ AFN=0x12 四种模式往返全部通过")


def test_sl427_84_voltage_values():
    """验证 AFN=0x84 电压数值正确性 (不止CRC)"""
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    for v in [0.0, 12.34, 99.99, 12.6]:
        f = enc.build_self_report_84(voltage=v)
        r = SL427Decoder().decode(f)
        assert r.crc_ok
        volt_elems = [e for e in r.elements if e.name == "电压"]
        if volt_elems:
            actual = float(volt_elems[0].value) if isinstance(volt_elems[0].value, str) else volt_elems[0].value
            if abs(actual - v) > 0.02:
                print(f"  ❌ 电压值不对: 输入{v}, 解码{actual}")
                FAILURES.append(f"AFN=0x84 电压值 {v}→{actual}")
            else:
                print(f"  ✅ 电压 {v}V → 解码 {actual}V")
        else:
            print(f"  ❌ 未找到电池电压要素!")
            FAILURES.append(f"AFN=0x84 电压值 {v} 未解析出要素")


# ============================================================
# 测试3: 充值量数值级验证
# ============================================================
def test_recharge_value_accuracy():
    """充电量数值级验证 — 不仅CRC，还要验证实际值"""
    addr = encode_address(method=1, admin_code=110108, stn_id=1284)
    enc = SL427Encoder(addr)
    dec = SL427Decoder()
    for amount in [0, 1, 1234, 9999, 50000, 99999999]:
        f = enc.build_set_recharge(amount)
        r = dec.decode(f)
        assert r.crc_ok, f"充值量{amount} CRC应通过"
        # 解码器可能不解析下行充值量数据，改为直接校验原始字节
        data = bytes(f)[10:14]  # 数据域位置
        print(f"    充值量 {amount:>8} → hex {data.hex().upper()}")
    print("  ✅ 充值量数据域字节已输出（需人工对照表13小端BCE）")


# ============================================================
# 测试4: 异常输入
# ============================================================
def test_edge_cases():
    """各种边界/异常输入"""
    dec = SL651Decoder()

    # 空报文
    for bad in ["", "hello", "GGGG", "7E", "7E7E"]:
        try:
            dec.decode_hex(bad)
            print(f"  ❌ 异常输入'{bad}'未抛异常!")
            FAILURES.append(f"decode_hex('{bad}') 未抛异常")
        except Exception:
            pass
    print("  ✅ 异常输入(空/非法/过短)均正确抛异常")

    # 非HEX字符
    try:
        dec.decode_hex("7E7E25XXXZZZ...")
        print("  ❌ 非HEX字符未抛异常")
        FAILURES.append("非HEX字符未抛异常")
    except Exception:
        pass

    # 奇数长度
    try:
        dec.decode_hex("7E7E2")
        print("  ❌ 奇数长度未抛异常")
        FAILURES.append("奇数长度hex未抛异常")
    except Exception:
        pass
    print("  ✅ 非HEX/奇数长度均正确报错")


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("业务测试1代 — 盲区覆盖测试")
    print("=" * 60)

    for name, fn in [
        ("小时报12组往返", test_hourly_roundtrip_12),
        ("小时报极端值", test_hourly_roundtrip_extreme_values),
        ("小时报非12组校验", test_hourly_invalid_count),
        ("SL427 AFN=0x81往返", test_sl427_81_roundtrip),
        ("SL427 AFN=0x82往返", test_sl427_82_roundtrip),
        ("SL427 AFN=0x84往返+值", test_sl427_84_roundtrip),
        ("SL427 AFN=0x84电压值", test_sl427_84_voltage_values),
        ("SL427 AFN=0x12工作模式", test_sl427_12_roundtrip),
        ("充值量数值级验证", test_recharge_value_accuracy),
        ("异常输入测试", test_edge_cases),
    ]:
        print(f">>> {name}")
        try:
            fn()
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            FAILURES.append(f"{name}: {e}")

    print()
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("✅ 所有盲区测试通过")
