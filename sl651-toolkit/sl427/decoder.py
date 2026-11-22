"""SL427-2021 水资源监测数据传输规约 解码器。

帧结构: 68 L 68 | C | A(5B) | AFN | data... | CS(CRC8) | 16
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sl651.bcd import (
    bcd_bytes_to_int,
    bcd_bytes_to_int_le,
    bytes_to_hex,
    bytes_to_hex_compact,
    safe_bcd_to_int,
)
from sl651.crc import crc8
from sl651.errors import DecodeError
from . import constants as C


@dataclass
class ElementValue:
    """单个要素解析结果。"""
    name: str
    value: str
    unit: str
    raw: str
    editable: bool = True
    byte_len: int = 0
    decimal: int = 0
    signed: bool = False
    is_time: bool = False


@dataclass
class DecodedMessage:
    """SL427 报文解析结果。"""

    hex_input: str = ""
    direction: str = ""
    ctrl_info: dict = field(default_factory=dict)
    ctrl_func_name: str = ""
    addr_display: str = ""
    afn: int = 0
    afn_name: str = ""
    data_len: int = 0
    crc_calc: int = 0
    crc_recv: int = 0
    crc_ok: bool = True
    elements: list[ElementValue] = field(default_factory=list)
    special_info: dict | None = None
    byte_map: str = ""
    frame_length: int = 0
    reassembled: bool = False
    packet_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "ctrl_func_name": self.ctrl_func_name,
            "addr": self.addr_display,
            "afn": f"0x{self.afn:02X}",
            "afn_name": self.afn_name,
            "crc_ok": self.crc_ok,
            "crc_calc": f"0x{self.crc_calc:02X}",
            "crc_recv": f"0x{self.crc_recv:02X}",
            "elements": [
                {"name": e.name, "value": e.value, "unit": e.unit, "raw": e.raw}
                for e in self.elements
            ],
            "frame_length": self.frame_length,
            "data_len": self.data_len,
            "reassembled": self.reassembled,
            "packet_count": self.packet_count,
            "warnings": list(self.warnings),
        }


def _fill_element(definition: dict, chunk: bytes, item_len: int) -> ElementValue:
    """构造缺测填充要素（值 '-'，保留原始填充字节）。"""
    return ElementValue(
        name=definition["name"], value="-", unit=definition["unit"],
        raw=bytes_to_hex_compact(chunk), byte_len=item_len,
        decimal=definition["decimal"], signed=definition["signed"],
    )


def _parse_water_amount(data: bytes) -> tuple[str, str]:
    """累计水量 5B 小端 BCD（表36），BYTE5 高半字节为 0；0xAA/0xFF 为缺测。"""
    hex_str = bytes_to_hex_compact(data)
    if _is_fill(data):
        return ("-", hex_str)
    try:
        v = bcd_bytes_to_int_le(data)
    except ValueError:
        return ("-", hex_str)
    return (str(v), hex_str)


def _parse_water_quality(
    data: bytes, *, single_bit: int | None = None,
    warnings: list[str] | None = None,
) -> tuple[list[ElementValue], int]:
    """水质参数（表18）：5B 位图 + N×4B 小端 BCD；single_bit 用于 B1 单参数。"""
    out: list[ElementValue] = []

    def _spec(bit: int) -> tuple[str, str, int]:
        if bit < len(C.WATER_QUALITY_SPECS):
            return C.WATER_QUALITY_SPECS[bit]
        return (f"参数{bit}", "", 0)

    if _is_fill(data) or (single_bit is None and len(data) >= 5 and _is_fill(data[:5])):
        fill_name = _spec(single_bit)[0] if single_bit is not None else "水质参数"
        return [ElementValue(name=fill_name, value="-", unit="",
                             raw=bytes_to_hex_compact(data), editable=False)], len(data)
    if single_bit is not None:
        if len(data) < 4:
            return out, 0
        seg = data[:4]
        name, unit, dec = _spec(single_bit)
        raw = bytes_to_hex_compact(seg)
        if _is_fill(seg):
            out.append(ElementValue(name=name, value="-", unit=unit, raw=raw,
                                    byte_len=4, decimal=dec, editable=False))
            return out, 4
        try:
            v = bcd_bytes_to_int_le(seg)
        except ValueError:
            out.append(ElementValue(name=name, value="-", unit=unit, raw=raw,
                                    byte_len=4, decimal=dec, editable=False))
            return out, 4
        out.append(ElementValue(name=name, value=f"{v / (10 ** dec):.{dec}f}",
                                unit=unit, raw=raw, byte_len=4, decimal=dec,
                                editable=False))
        return out, 4

    if len(data) < 5:
        return out, 0
    mask = int.from_bytes(data[:5], "little")
    pos = 5
    for bit in range(40):
        if not ((mask >> bit) & 1):
            continue
        if pos + 4 > len(data):
            if warnings is not None:
                warnings.append(
                    f"水质位图有置位参数但数据不足 4B（位 {bit}），剩余未解析")
            break
        seg = data[pos:pos + 4]
        pos += 4
        name, unit, dec = _spec(bit)
        raw = bytes_to_hex_compact(seg)
        if _is_fill(seg):
            out.append(ElementValue(name=name, value="-", unit=unit, raw=raw,
                                    byte_len=4, decimal=dec, editable=False))
            continue
        try:
            v = bcd_bytes_to_int_le(seg)
        except ValueError:
            out.append(ElementValue(name=name, value="-", unit=unit, raw=raw,
                                    byte_len=4, decimal=dec, editable=False))
            continue
        out.append(ElementValue(name=name, value=f"{v / (10 ** dec):.{dec}f}",
                                unit=unit, raw=raw, byte_len=4, decimal=dec,
                                editable=False))
    return out, pos


def _parse_weather(data: bytes) -> tuple[list[ElementValue], int]:
    """气象参数（表40，8B）：气压3B(hPa) + 风速(含风向)3B + 有符号气温2B。"""
    out: list[ElementValue] = []
    if len(data) < 8:
        return out, 0
    seg = data[:8]
    # 气压：BYTE1 十位/个位，BYTE2 千位/百位，BYTE3 万位；单位 10^2 Pa = hPa
    p = seg[:3]
    if _is_fill(p):
        out.append(ElementValue(name="气压", value="-", unit="hPa",
                                raw=bytes_to_hex_compact(p), byte_len=3, decimal=0))
    else:
        try:
            pv = bcd_bytes_to_int_le(p)
            out.append(ElementValue(name="气压", value=str(pv), unit="hPa",
                                    raw=bytes_to_hex_compact(p), byte_len=3, decimal=0))
        except ValueError:
            out.append(ElementValue(name="气压", value="-", unit="hPa",
                                    raw=bytes_to_hex_compact(p), byte_len=3, decimal=0))

    # 风速/风向：BYTE4 十分位/百分位；BYTE5 个位/十位；BYTE6 风向/百位
    wind = seg[3:6]
    if _is_fill(wind):
        out.append(ElementValue(name="风速", value="-", unit="m/s",
                                raw=bytes_to_hex_compact(wind), byte_len=2, decimal=2))
        out.append(ElementValue(name="风向", value="-", unit="",
                                raw=bytes_to_hex_compact(wind[2:]), byte_len=1, decimal=0))
    else:
        try:
            tenths = (wind[0] >> 4) & 0x0F
            hundredths = wind[0] & 0x0F
            units = (wind[1] >> 4) & 0x0F
            tens = wind[1] & 0x0F
            direction = (wind[2] >> 4) & 0x0F
            hundreds = wind[2] & 0x0F
            if max(tenths, hundredths, units, tens, hundreds) > 9 or direction > 8:
                raise ValueError("气象风速/风向非 BCD")
            speed = hundreds * 100 + tens * 10 + units + tenths / 10 + hundredths / 100
            out.append(ElementValue(name="风速", value=f"{speed:.2f}", unit="m/s",
                                    raw=bytes_to_hex_compact(wind[:2]), byte_len=2, decimal=2))
            out.append(ElementValue(name="风向", value=str(direction), unit="",
                                    raw=bytes_to_hex_compact(wind[2:]), byte_len=1, decimal=0))
        except ValueError:
            out.append(ElementValue(name="风速", value="-", unit="m/s",
                                    raw=bytes_to_hex_compact(wind), byte_len=2, decimal=2))
            out.append(ElementValue(name="风向", value="-", unit="",
                                    raw=bytes_to_hex_compact(wind[2:]), byte_len=1, decimal=0))

    # 气温：BYTE7 个位/十分位；BYTE8 符号(0/F)+十位
    temp = seg[6:8]
    if _is_fill(temp):
        out.append(ElementValue(name="气温", value="-", unit="℃",
                                raw=bytes_to_hex_compact(temp), byte_len=2, decimal=1))
    else:
        try:
            units = (temp[0] >> 4) & 0x0F
            tenths = temp[0] & 0x0F
            sign = (temp[1] >> 4) & 0x0F
            tens = temp[1] & 0x0F
            if max(units, tenths, tens) > 9 or sign not in (0x00, 0x0F):
                raise ValueError("气象气温非 BCD")
            tv = tens * 10 + units + tenths / 10
            if sign == 0x0F:
                tv = -tv
            out.append(ElementValue(name="气温", value=f"{tv:.1f}", unit="℃",
                                    raw=bytes_to_hex_compact(temp), byte_len=2, decimal=1))
        except ValueError:
            out.append(ElementValue(name="气温", value="-", unit="℃",
                                    raw=bytes_to_hex_compact(temp), byte_len=2, decimal=1))
    return out, 8


def _parse_soil_record(chunk: bytes) -> list[ElementValue]:
    """土壤含水率 4B（表42）：前 2B 含水率(0.1%) + 后 2B 采集深度(cm)。"""
    raw = bytes_to_hex_compact(chunk)
    if _is_fill(chunk):
        return [
            ElementValue(name="土壤含水率", value="-", unit="%", raw=raw,
                         byte_len=2, decimal=1),
            ElementValue(name="采集深度", value="-", unit="cm", raw=raw,
                         byte_len=2, decimal=0),
        ]
    try:
        moisture = bcd_bytes_to_int_le(chunk[:2]) / 10
    except ValueError:
        moisture = "-"
    try:
        depth = bcd_bytes_to_int_le(chunk[2:4])
    except ValueError:
        depth = "-"
    return [
        ElementValue(name="土壤含水率", value=moisture, unit="%", raw=raw,
                     byte_len=2, decimal=1),
        ElementValue(name="采集深度", value=depth, unit="cm", raw=raw,
                     byte_len=2, decimal=0),
    ]


def _parse_one_scalar(func_code: int, chunk: bytes,
                      definition: dict) -> list[ElementValue]:
    """解析一条定长标量记录（0x01/02/04/05/06/08/09/0C/0D/0E/0F）。"""
    if _is_fill(chunk):
        return [_fill_element(definition, chunk, definition["byteLen"])]
    hex_str = bytes_to_hex_compact(chunk)
    if definition["signed"]:
        display, raw = _parse_signed_bcd(chunk, definition["decimal"])
        return [ElementValue(name=definition["name"], value=display,
                             unit=definition["unit"], raw=raw,
                             byte_len=definition["byteLen"],
                             decimal=definition["decimal"], signed=True)]
    v = bcd_bytes_to_int_le(chunk)
    dec = definition["decimal"]
    return [ElementValue(name=definition["name"],
                         value=f"{v / (10 ** dec):.{dec}f}",
                         unit=definition["unit"], raw=hex_str,
                         byte_len=definition["byteLen"], decimal=dec)]


def _parse_parameter_records(
    func_code: int, data: bytes, *, context: str = "b0",
    warnings: list[str] | None = None, max_records: int | None = None,
    param_byte: int | None = None,
) -> tuple[list[ElementValue], int]:
    """按类型码解析参数记录，返回 (要素, 已消费字节数)。

    统一处理 B0/C0/81/82/B1/FF/综合参数的差异：
    - scalar：按 byteLen 逐条（array=False 只取首条）；
    - flow_pair：流量5B + 累计水量5B（表35/表36）；
    - weather：8B 拆 4 值；water_quality：5B 位图 + N×4B 或 B1 单参数 4B；
    - soil：4B 拆含水率/深度两值。
    """
    definition = C.CTRL_FUNC_MAP.get(func_code)
    if not definition or definition["byteLen"] == 0:
        return [], 0
    kind = definition.get("kind", "scalar")
    items: list[ElementValue] = []
    pos = 0
    records = 0

    while pos < len(data):
        if max_records is not None and records >= max_records:
            break
        if kind == "flow_pair":
            if pos + 10 > len(data):
                if pos + 5 <= len(data):
                    # 非标实现可能只带流量、不带累计水量：按 5B 降级并留 warning
                    flow = data[pos:pos + 5]
                    pos += 5
                    records += 1
                    if _is_fill(flow):
                        items.append(_fill_element({"name": "流量", "unit": "m³/s",
                                                    "decimal": definition["decimal"],
                                                    "signed": True}, flow, 5))
                    else:
                        display, raw, unit_str = _parse_flow(flow, definition["decimal"])
                        items.append(ElementValue(
                            name="流量", value=display, unit=unit_str, raw=raw,
                            byte_len=5, decimal=definition["decimal"], signed=True))
                    if warnings is not None:
                        warnings.append("0x03 缺少累计水量字段，按单流量 5B 降级解析")
                break
            flow = data[pos:pos + 5]
            water = data[pos + 5:pos + 10]
            pos += 10
            records += 1
            flow_def = dict(definition)
            flow_def["name"] = "流量"
            if _is_fill(flow):
                items.append(_fill_element(flow_def, flow, 5))
            else:
                display, raw, unit_str = _parse_flow(flow, definition["decimal"])
                items.append(ElementValue(
                    name="流量", value=display, unit=unit_str, raw=raw,
                    byte_len=5, decimal=definition["decimal"], signed=True))
            wv, wraw = _parse_water_amount(water)
            items.append(ElementValue(
                name="累计水量", value=wv, unit="m³", raw=wraw,
                byte_len=5, decimal=0))
        elif kind == "weather":
            if pos + 8 > len(data):
                break
            parsed, used = _parse_weather(data[pos:pos + 8])
            items.extend(parsed)
            pos += used
            records += 1
        elif kind == "water_quality":
            single_bit = None
            if context == "b1" and param_byte is not None:
                # 兼容两种 B1 形态：合规 5B 位图 + N×4B；或单参数 4B。
                remaining = len(data) - pos
                block = data[pos:]
                is_bitmap = (
                    remaining >= 9 and (remaining - 5) % 4 == 0
                    and int.from_bytes(block[:5], "little").bit_count()
                    == (remaining - 5) // 4
                )
                if not is_bitmap:
                    single_bit = param_byte & 0x0F
            parsed, used = _parse_water_quality(
                data[pos:], single_bit=single_bit, warnings=warnings)
            if used == 0:
                break
            items.extend(parsed)
            pos += used
            records += 1
        elif kind == "soil":
            if pos + 4 > len(data):
                break
            items.extend(_parse_soil_record(data[pos:pos + 4]))
            pos += 4
            records += 1
        else:
            item_len = definition["byteLen"]
            if pos + item_len > len(data):
                break
            chunk = data[pos:pos + item_len]
            items.extend(_parse_one_scalar(func_code, chunk, definition))
            pos += item_len
            records += 1
            if not definition["array"]:
                break
    return items, pos


def _parse_ctrl_func_data(func_code: int, data_bytes: bytes,
                          max_items: int | None = None) -> list[ElementValue]:
    """兼容包装：返回要素列表（不返回消费量）。新代码请用 _parse_parameter_records。"""
    items, _ = _parse_parameter_records(
        func_code, data_bytes, context="raw", max_records=max_items)
    return items


def _extend_parameter_records(
    elements: list[ElementValue], func_code: int, data: bytes, *,
    context: str, warnings: list[str],
) -> int:
    """解析并把要素追加到 elements；尾随字节统一写 warning（不静默丢弃）。"""
    parsed, consumed = _parse_parameter_records(
        func_code, data, context=context, warnings=warnings)
    elements.extend(parsed)
    if consumed < len(data):
        warnings.append(
            f"参数字段 {len(data)}B，已解析 {consumed}B，"
            f"剩余 {len(data) - consumed}B 未展开")
    return consumed


def _parse_signed_bcd(data: bytes, decimal: int) -> tuple[str, str]:
    """解析有符号 BCD 值（小端）。高半字节 0xF=负号，0xA~0xE 为非法数据。"""
    hex_str = bytes_to_hex_compact(data)
    last = data[-1]
    hi = (last >> 4) & 0x0F
    if 0x0A <= hi <= 0x0E:
        return ("-", hex_str)
    neg = hi == 0x0F
    mod = bytearray(data)
    mod[-1] = last & 0x0F
    try:
        v = bcd_bytes_to_int_le(bytes(mod))
    except ValueError:
        return ("-", hex_str)
    d = 10 ** decimal
    r = (-1 if neg else 1) * v / d
    return (f"{r:.{decimal}f}", hex_str)


def _parse_flow(data: bytes, decimal: int) -> tuple[str, str, str]:
    """解析流量/水量（0x03），按规范表35。
    5B：BYTE5 D7~D6=符号(00B=正,11B=负), D5~D4=单位(00B=m³/s,11B=m³/h)。
    0xAA 填充 = 缺测。
    """
    hex_str = bytes_to_hex_compact(data)
    if _is_fill(data):
        return ("-", hex_str, "m³/s")
    byte5 = data[-1]
    sign_bits = (byte5 >> 6) & 0x03
    unit_bits = (byte5 >> 4) & 0x03
    neg = sign_bits == 0x03
    unit_map = {0x00: "m³/s", 0x03: "m³/h"}
    unit_name = unit_map.get(unit_bits, f"m³/s(0x{unit_bits:02X})")
    mod = bytearray(data[:4])
    mod.append(byte5 & 0x0F)
    v = bcd_bytes_to_int_le(bytes(mod))
    d = 10 ** decimal
    r = (-1 if neg else 1) * v / d
    return (f"{r:.{decimal}f}", hex_str, unit_name)


def _parse_comprehensive(data: bytes, warnings: list[str] | None = None) -> list[ElementValue]:
    """解析综合参数（0x0E 功能码，表45）。

    D0~D7 依次为水质/土壤含水率/功率/气象/闸位/流量/水位/雨量；每个置位参数
    在数据区出现且仅出现一次，按各自的块长消费（0x03=10B、0x07=8B、
    0x0A=5+N×4B、0x0B=4B，其余按 byteLen）。
    """
    if len(data) == 0:
        return []
    if warnings is None:
        warnings = []
    bit_flag = data[0]
    offset = 1
    items: list[ElementValue] = []
    for i in range(len(C.COMP_BITS)):
        if not (bit_flag & (1 << i)):
            continue
        func_code = C.COMP_BITS[i]
        parsed, consumed = _parse_parameter_records(
            func_code, data[offset:], context="comprehensive",
            warnings=warnings, max_records=1)
        if consumed == 0:
            warnings.append(
                f"综合参数 0x0E 数据不足：bit{i}(0x{func_code:02X}) 无法解析，"
                f"剩余 {max(0, len(data) - offset)} 字节"
            )
            break
        items.extend(parsed)
        offset += consumed
    if offset < len(data):
        warnings.append(
            f"综合参数 0x0E 剩余 {len(data) - offset} 字节未展开")
    return items


def _statistical_rain_type_name(rtype: int) -> str:
    """表54：D7~D6=类别（00 时段/01 小时/10 日/11 测试），D5~D0=时段长度。"""
    cls = (rtype >> 6) & 0x03
    length = rtype & 0x3F
    if cls == 0:
        return f"时段降雨量({length * 5}min)"
    if cls == 1:
        return f"小时降雨量({length}h)"
    if cls == 2:
        return f"日降雨量({length}d)"
    return "测试/累计雨量"


def _parse_statistical_rainfall(data: bytes) -> list[ElementValue]:
    """解析上行统计雨量（0x0E），规范7.5.6 c：1B 雨量类型 + 3B 雨量数据（小端 BCD）。

    表33：3B 雨量数据以 0.1mm 为单位；表54：类型字节 D7~D6=类别、D5~D0=时长。
    """
    items = []
    pos = 0
    while pos + 4 <= len(data):
        rtype = data[pos]
        rdata = data[pos + 1: pos + 4]
        pos += 4
        try:
            v = bcd_bytes_to_int_le(rdata)
            val = f"{v / 10:.1f}"
        except (ValueError, IndexError):
            val = "-"
        items.append(ElementValue(
            name=f"统计雨量({_statistical_rain_type_name(rtype)})",
            value=val, unit="mm",
            raw=bytes_to_hex_compact(bytes([rtype]) + rdata),
            byte_len=4, decimal=1,
        ))
    return items


def _is_fill(data: bytes) -> bool:
    """是否为规约「未采集/无数据」填充：全 0xAA 或全 0xFF（规约行 1172/900）。"""
    return bool(data) and (all(b == 0xAA for b in data) or all(b == 0xFF for b in data))


def _parse_alarm(data: bytes) -> list[ElementValue]:
    """解析告警状态。全 0xAA/0xFF 填充（缺测）降级为单个 '-' 要素。"""
    if _is_fill(data):
        return [ElementValue(name="告警状态", value="-", unit="",
                             raw=bytes_to_hex_compact(data), editable=False)]
    num = data[0] | (data[1] << 8)
    items = []
    for ab in C.ALARM_BITS:
        bv = (num >> ab["bit"]) & 1
        items.append(ElementValue(
            name=ab["name"], value=ab["map"].get(bv, "-"),
            unit="", raw=str(bv), editable=False,
        ))
    return items


def _parse_terminal(data: bytes) -> list[ElementValue]:
    """解析终端状态。全 0xAA/0xFF 填充（缺测）降级为单个 '-' 要素。"""
    if _is_fill(data):
        return [ElementValue(name="终端状态", value="-", unit="",
                             raw=bytes_to_hex_compact(data), editable=False)]
    num = data[0] | (data[1] << 8)
    items = []
    for tb in C.TERMINAL_BITS:
        bits = tb["bit"]
        if isinstance(bits, list):
            bv = (num >> bits[0]) & ((1 << (bits[1] - bits[0] + 1)) - 1)
        else:
            bv = (num >> bits) & 1
        items.append(ElementValue(
            name=tb["name"], value=tb["map"].get(bv, "-"),
            unit="", raw=str(bv), editable=False,
        ))
    return items

def _safe_bcd_le(data: bytes) -> int | None:
    """小端 BCD 解析：仅对规约合法的 0xAA/0xFF 缺测填充返回 None（降级 '-'）。

    非填充的非法半字节（如 0x1A）仍抛 ValueError，由上层包装为 DecodeError，
    保持「畸形数据被拒绝」的契约（审计 v2.4 L-3）。
    """
    if _is_fill(data):
        return None
    return bcd_bytes_to_int_le(data)


def _bcd_le_signed(data: bytes) -> int | str:
    """小端 BCD（末字节 D7 为符号位，1=负）-> 有符号整数；填充/无效返回 '-'。"""
    if not data or _is_fill(data):
        return "-"
    last = data[-1]
    neg = bool(last & 0x80)
    clean = bytes(data[:-1]) + bytes([last & 0x7F])
    v = _safe_bcd_le(clean)
    if v is None:
        return "-"
    return -v if neg else v


def _parse_flow_limit_427(seg: bytes) -> tuple[float | str, str]:
    """解析 5B 流量参数（表20，小端 BCD，BYTE5 高半字节=符号/单位）。

    0xAA/0xFF 填充（缺测）返回 ('-', '')。
    """
    if len(seg) < 5:
        return 0.0, ""
    if all(b == 0xAA for b in seg) or all(b == 0xFF for b in seg):
        return "-", ""
    high = seg[4]
    sign = -1 if (high & 0xC0) == 0xC0 else 1
    unit = "m³/h" if (high & 0x30) == 0x30 else "m³/s"
    base = _safe_bcd_le(seg[:4])
    if base is None:
        return "-", unit
    scaled = base + (high & 0x0F) * 10 ** 8
    return sign * scaled / 1000.0, unit


def _parse_switch_record_427(seg: bytes) -> str:
    """解析 5B 中继切换时间（表32：分 时 日 星期月 年 BCD）。"""
    if len(seg) < 5:
        return bytes_to_hex_compact(seg)
    if _is_fill(seg):
        return "-"
    minute = safe_bcd_to_int(seg[0])
    hour = safe_bcd_to_int(seg[1])
    day = safe_bcd_to_int(seg[2])
    wm = seg[3]
    month = wm & 0x1F
    year = safe_bcd_to_int(seg[4])
    if None in (minute, hour, day, year):
        return f"无效时间({bytes_to_hex_compact(seg)})"
    return f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _parse_level_limits_427(seg: bytes) -> list[ElementValue]:
    """解析 7B 水位基值/上下限（表15/16，小端 BCD，基值第3字节 D7 符号位）。

    0xAA/0xFF 填充（缺测）降级显示 '-'。
    """
    if len(seg) < 7:
        return []
    fill = all(b == 0xAA for b in seg) or all(b == 0xFF for b in seg)
    b0, b1, b2 = seg[0], seg[1], seg[2]
    if fill:
        base = lower = upper = "-"
    else:
        base_scaled = _safe_bcd_le(bytes([b0, b1, b2 & 0x7F]))
        low_v = _safe_bcd_le(seg[3:5])
        up_v = _safe_bcd_le(seg[5:7])
        if base_scaled is None or low_v is None or up_v is None:
            base = lower = upper = "-"
        else:
            base = base_scaled / 100.0
            if b2 & 0x80:
                base = -base
            lower = low_v / 100.0
            upper = up_v / 100.0
    return [
        ElementValue(name="水位基值", value=base, unit="m",
                     raw=bytes_to_hex_compact(seg[:3]), editable=False, decimal=2),
        ElementValue(name="水位下限", value=lower, unit="m",
                     raw=bytes_to_hex_compact(seg[3:5]), editable=False, decimal=2),
        ElementValue(name="水位上限", value=upper, unit="m",
                     raw=bytes_to_hex_compact(seg[5:7]), editable=False, decimal=2),
    ]


def _parse_pressure_limits_427(seg: bytes) -> list[ElementValue]:
    """解析 8B 水压上/下限（表17，4B 小端 BCD ×2）。0xAA/0xFF 填充降级 '-'。"""
    if len(seg) < 8:
        return []
    fill = all(b == 0xAA for b in seg) or all(b == 0xFF for b in seg)
    if fill:
        upper = lower = "-"
    else:
        up_v = _safe_bcd_le(seg[:4])
        low_v = _safe_bcd_le(seg[4:8])
        if up_v is None or low_v is None:
            upper = lower = "-"
        else:
            upper = up_v / 100.0
            lower = low_v / 100.0
    return [
        ElementValue(name="水压上限", value=upper, unit="kPa",
                     raw=bytes_to_hex_compact(seg[:4]), editable=False, decimal=2),
        ElementValue(name="水压下限", value=lower, unit="kPa",
                     raw=bytes_to_hex_compact(seg[4:8]), editable=False, decimal=2),
    ]


def _parse_water_quality_427(
    data: bytes, warnings: list[str] | None = None,
) -> list[ElementValue]:
    """解析水质参数种类及上/下限（表18，5B 位图 + N×4B 小端 BCD）。"""
    out, consumed = _parse_water_quality(data, warnings=warnings)
    if warnings is not None and consumed and consumed < len(data):
        warnings.append(
            f"水质参数数据 {len(data)}B，已解析 {consumed}B，"
            f"剩余 {len(data) - consumed}B 未展开")
    return out


def _parse_channel_427(data: bytes) -> list[ElementValue]:
    """解析主备信道类型及中心站地址（§7.2.24）。"""
    out: list[ElementValue] = []
    type_names = {0x01: "短信", 0x02: "IPV4", 0x03: "北斗卫星"}
    addr_len = {0x01: 7, 0x02: 7, 0x03: 3}
    pos = 0
    for label in ("主信道", "备用信道"):
        if pos >= len(data):
            break
        t = data[pos]
        pos += 1
        if t in (0xAA, 0xFF):
            has_second = pos < len(data) and data[pos] in (0xAA, 0xFF)
            raw = bytes([t]) + (bytes([data[pos]]) if has_second else b"")
            out.append(ElementValue(
                name=label,
                value="无",
                unit="", raw=bytes_to_hex_compact(raw), editable=False,
            ))
            if has_second:
                pos += 1  # 0xAAAA / 0xFFFF 两字节
            continue
        n = addr_len.get(t, 0)
        addr = data[pos:pos + n]
        pos += n
        out.append(ElementValue(
            name=label,
            value=f"{type_names.get(t, f'0x{t:02X}')} {bytes_to_hex_compact(addr)}",
            unit="", raw=bytes_to_hex_compact(bytes([t]) + addr), editable=False,
        ))
    return out


def _warn_tail(warnings: list[str] | None, total: int, consumed: int,
               label: str) -> None:
    if warnings is not None and consumed < total:
        warnings.append(
            f"{label} 数据 {total}B，已解析 {consumed}B，"
            f"剩余 {total - consumed}B 未展开")


def _parse_query_response(
    afn_hex: str, data: bytes, warnings: list[str] | None = None,
) -> list[ElementValue]:
    """解析查询类响应帧（AFN=50H~65H，规约 7.3.2~7.3.21）。"""
    out: list[ElementValue] = []
    raw = bytes_to_hex_compact(data)

    fixed_len = {
        "50": 5, "51": 6, "52": 1, "54": 2, "55": 9, "56": 8,
        "5d": 64, "5e": 4, "5f": 12, "60": 1,
    }.get(afn_hex)
    if (warnings is not None and fixed_len is not None
            and len(data) != fixed_len):
        warnings.append(
            f"AFN={afn_hex.upper()}H 数据域 {len(data)}B，规约固定 {fixed_len}B")

    if afn_hex == "50":
        if len(data) >= 5:
            out.append(ElementValue(name="站点地址", value=_format_addr(data[:5]),
                                    unit="", raw=bytes_to_hex_compact(data[:5]),
                                    editable=False))
    elif afn_hex == "51":
        if len(data) >= 6:
            out.append(ElementValue(name="站点时钟", value=_fmt_time_427(data[:6] + b"\x00"),
                                    unit="", raw=bytes_to_hex_compact(data[:6]),
                                    editable=False, is_time=True))
    elif afn_hex == "52":
        if len(data) >= 1:
            mode = data[0]
            if mode in (0xAA, 0xFF):
                name = "-"
            else:
                name = {0: "兼容", 1: "自报", 2: "查询/应答", 3: "调试"}.get(mode, f"未知({mode})")
            out.append(ElementValue(name="工作模式", value=name, unit="",
                                    raw=f"{mode:02X}", editable=False))
    elif afn_hex == "53":
        if len(data) >= 2:
            if _is_fill(data[:2]):
                out.append(ElementValue(name="数据自报种类", value="-",
                                        unit="", raw=raw, editable=False))
            else:
                mask = data[0] | (data[1] << 8)
                names = [C.RT_KINDS_REPORT[i] for i in range(16) if (mask >> i) & 1]
                out.append(ElementValue(name="数据自报种类",
                                        value="、".join(names) or "无",
                                        unit="", raw=raw, editable=False))
            for i in range((len(data) - 2) // 2):
                iv = _safe_bcd_le(data[2 + i * 2:4 + i * 2])
                label = C.RT_KINDS_REPORT[i] if i < len(C.RT_KINDS_REPORT) else f"#{i}"
                out.append(ElementValue(name=f"自报间隔[{label}]",
                                        value=iv if iv is not None else "-",
                                        unit="min", raw=raw, editable=False))
            if warnings is not None and len(data) != 30:
                warnings.append(
                    f"AFN=53H 数据域 {len(data)}B，规约固定 30B（14 个间隔），"
                    "按实际长度解析")
        else:
            out.append(ElementValue(name="数据自报种类及间隔", value=f"{len(data)} 字节",
                                    unit="bytes", raw=raw, editable=False))
    elif afn_hex == "54":
        if len(data) >= 2:
            if _is_fill(data[:2]):
                out.append(ElementValue(name="实时数据种类", value="-",
                                        unit="", raw=raw, editable=False))
            else:
                mask = data[0] | (data[1] << 8)
                names = [C.CTRL_FUNC_MAP.get(i, {}).get("name", f"0x{i:02X}")
                         for i in range(16) if (mask >> i) & 1]
                out.append(ElementValue(name="实时数据种类", value="、".join(names) or "无",
                                        unit="", raw=f"{mask:04X}", editable=False))
    elif afn_hex == "55":
        if len(data) >= 9:
            recharge = _safe_bcd_le(data[:4])
            out.append(ElementValue(name="最近充值量",
                                    value=recharge if recharge is not None else "-",
                                    unit="m³", raw=bytes_to_hex_compact(data[:4]),
                                    editable=False))
            out.append(ElementValue(name="剩余水量", value=_bcd_le_signed(data[4:9]),
                                    unit="m³", raw=bytes_to_hex_compact(data[4:9]),
                                    editable=False))
    elif afn_hex == "56":
        if len(data) >= 8:
            alarm_v = _safe_bcd_le(data[:3])
            out.append(ElementValue(name="剩余水量报警值",
                                    value=alarm_v if alarm_v is not None else "-",
                                    unit="m³", raw=bytes_to_hex_compact(data[:3]),
                                    editable=False))
            out.append(ElementValue(name="剩余水量", value=_bcd_le_signed(data[3:8]),
                                    unit="m³", raw=bytes_to_hex_compact(data[3:8]),
                                    editable=False))
    elif afn_hex == "5e":
        if len(data) >= 4:
            out.extend(_parse_alarm(data[:2]))
            out.extend(_parse_terminal(data[2:4]))
    elif afn_hex == "5f":
        labels = [("A相电压", "V"), ("B相电压", "V"), ("C相电压", "V"),
                  ("A相电流", "A"), ("B相电流", "A"), ("C相电流", "A")]
        for i, (lab, unit) in enumerate(labels):
            seg = data[i * 2:i * 2 + 2]
            if len(seg) == 2:
                val = "-" if _is_fill(seg) else int.from_bytes(seg, "little")
                out.append(ElementValue(name=lab, value=val,
                                        unit=unit, raw=bytes_to_hex_compact(seg),
                                        editable=False))
    elif afn_hex == "60":
        if data:
            val = "-" if data[0] in (0xAA, 0xFF) else data[0]
            out.append(ElementValue(name="中继引导码长值", value=val, unit="s",
                                    raw=f"{data[0]:02X}", editable=False))
    elif afn_hex == "62":
        n = len(data) // 5
        for i in range(n):
            seg = data[i * 5:i * 5 + 5]
            out.append(ElementValue(name=f"转发站地址[{i + 1}]", value=_format_addr(seg),
                                    unit="", raw=bytes_to_hex_compact(seg),
                                    editable=False))
        _warn_tail(warnings, len(data), n * 5, "AFN=62H")
    elif afn_hex == "5d":
        n = min(len(data) // 2, len(C.EVENT_RECORDS))
        for i in range(n):
            seg = data[i * 2:i * 2 + 2]
            cnt = "-" if _is_fill(seg) else int.from_bytes(seg, "little")
            out.append(ElementValue(name=f"事件记录[{C.EVENT_RECORDS[i]}]", value=cnt,
                                    unit="次", raw=bytes_to_hex_compact(seg),
                                    editable=False))
        _warn_tail(warnings, len(data), n * 2, "AFN=5DH")
    elif afn_hex == "57":
        # N×7B 水位基值/上下限 + 4B 终端机报警状态
        if len(data) >= 4:
            body, tail = data[:-4], data[-4:]
            for i in range(len(body) // 7):
                for e in _parse_level_limits_427(body[i * 7:i * 7 + 7]):
                    e.name = f"{e.name}[{i + 1}]"
                    out.append(e)
            _warn_tail(warnings, len(body), (len(body) // 7) * 7, "AFN=57H")
            out.extend(_parse_alarm(tail[:2]))
            out.extend(_parse_terminal(tail[2:4]))
    elif afn_hex == "58":
        # N×8B 水压上/下限 + 4B 终端机报警状态
        if len(data) >= 4:
            body, tail = data[:-4], data[-4:]
            for i in range(len(body) // 8):
                for e in _parse_pressure_limits_427(body[i * 8:i * 8 + 8]):
                    e.name = f"{e.name}[{i + 1}]"
                    out.append(e)
            _warn_tail(warnings, len(body), (len(body) // 8) * 8, "AFN=58H")
            out.extend(_parse_alarm(tail[:2]))
            out.extend(_parse_terminal(tail[2:4]))
    elif afn_hex in ("59", "5a"):
        out.extend(_parse_water_quality_427(data, warnings))
    elif afn_hex == "65":
        out.extend(_parse_channel_427(data))
    elif afn_hex == "63":
        if len(data) >= 2:
            if _is_fill(data[:2]):
                out.append(ElementValue(name="中继状态", value="-", unit="",
                                        raw=raw, editable=False))
            else:
                b1, b2 = data[0], data[1]
                out.append(ElementValue(name="中继自动切换/自报", value=f"0x{b1:02X}",
                                        unit="", raw=f"{b1:02X}", editable=False))
                flags = [
                    (0, "工作机A机", {1: "正常", 0: "故障"}),
                    (1, "工作机B机", {1: "正常", 0: "故障"}),
                    (2, "值班机", {1: "A机", 0: "B机"}),
                    (3, "转发", {1: "允许", 0: "不允许"}),
                    (4, "电源", {1: "报警", 0: "正常"}),
                    (5, "中继", {1: "故障报警", 0: "正常"}),
                ]
                for bit, name, mp in flags:
                    out.append(ElementValue(name=f"中继状态[{name}]",
                                            value=mp.get((b2 >> bit) & 1, "-"),
                                            unit="", raw=f"{b2:02X}", editable=False))
            rec = data[2:]
            for i in range(len(rec) // 5):
                seg = rec[i * 5:i * 5 + 5]
                out.append(ElementValue(name=f"切换记录[{i + 1}]",
                                        value=_parse_switch_record_427(seg),
                                        unit="", raw=bytes_to_hex_compact(seg),
                                        editable=False, is_time=True))
            _warn_tail(warnings, len(rec), (len(rec) // 5) * 5, "AFN=63H")
    elif afn_hex == "64":
        # 流量参数上限 N×5B + 报警(2B)+状态(2B)
        if len(data) >= 4:
            body, tail = data[:-4], data[-4:]
            n = len(body) // 5
            for i in range(n):
                seg = body[i * 5:i * 5 + 5]
                val, unit = _parse_flow_limit_427(seg)
                out.append(ElementValue(name=f"流量上限[{i + 1}]", value=val,
                                        unit=unit, raw=bytes_to_hex_compact(seg),
                                        editable=False))
            _warn_tail(warnings, len(body), n * 5, "AFN=64H")
            out.extend(_parse_alarm(tail[:2]))
            out.extend(_parse_terminal(tail[2:4]))
    else:
        out.append(ElementValue(name="查询响应数据", value=f"{len(data)} 字节",
                                unit="bytes", raw=raw, editable=False))
    return out


def _parse_control_response(
    afn_hex: str, data: bytes, warnings: list[str] | None = None,
) -> list[ElementValue]:
    """解析控制命令响应帧（AFN=90H~96H，规约 7.4）与配置响应（A0H~A2H）。"""
    out: list[ElementValue] = []
    raw = bytes_to_hex_compact(data)

    fixed_len = {
        "90": 1, "91": 1, "92": 1, "93": 1, "94": 1, "95": 1,
        "96": 2, "a0": 2,
    }.get(afn_hex)
    if (warnings is not None and fixed_len is not None
            and len(data) != fixed_len):
        warnings.append(
            f"AFN={afn_hex.upper()}H 数据域 {len(data)}B，规约固定 {fixed_len}B")

    if afn_hex == "90":
        if data:
            txt = "-" if data[0] in (0xAA, 0xFF) else (
                "执行完毕" if data[0] == 0x5A else f"0x{data[0]:02X}")
            out.append(ElementValue(name="复位响应", value=txt, unit="", raw=raw,
                                    editable=False))
    elif afn_hex == "91":
        if data:
            if data[0] in (0xAA, 0xFF):
                val = "-"
            else:
                names = [n for bit, n in ((0, "雨量"), (1, "水位"), (2, "水量"))
                         if (data[0] >> bit) & 1]
                val = "、".join(names) or "无"
            out.append(ElementValue(name="清空历史数据", value=val,
                                    unit="", raw=raw, editable=False))
    elif afn_hex in ("92", "93"):
        if data:
            act = "启动" if afn_hex == "92" else "关闭"
            if data[0] in (0xAA, 0xFF):
                txt = "-"
            else:
                code = data[0] & 0x0F
                is_valve = ((data[0] >> 4) & 0x0F) == 0x0F
                done = ((data[0] >> 4) & 0x0F) == 0x0A
                kind = "阀门/闸门" if is_valve else "水泵"
                txt = f"{kind}编号{code}" + (" 执行完毕" if done else "")
            out.append(ElementValue(name=f"{act}响应", value=txt, unit="", raw=raw,
                                    editable=False))
    elif afn_hex in ("94", "95"):
        if data:
            if data[0] in (0xAA, 0xFF):
                m = "-"
            else:
                low = data[0] & 0x0F
                m = "A机" if low == 0x09 else ("B机" if low == 0x06 else f"0x{low:02X}")
            out.append(ElementValue(name="切换响应", value=m, unit="", raw=raw,
                                    editable=False))
    elif afn_hex == "96":
        if len(data) >= 2:
            pw_v = _safe_bcd_le(data[:2])
            out.append(ElementValue(name="密码设置响应",
                                    value=pw_v if pw_v is not None else "-",
                                    unit="", raw=raw, editable=False))
    elif afn_hex == "a0":
        if len(data) >= 2:
            if _is_fill(data[:2]):
                out.append(ElementValue(name="需查询的实时数据种类", value="-",
                                        unit="", raw=raw, editable=False))
            else:
                mask = data[0] | (data[1] << 8)
                names = [C.RT_KINDS_QUERY[i] for i in range(16) if (mask >> i) & 1]
                out.append(ElementValue(name="需查询的实时数据种类",
                                        value="、".join(names) or "无",
                                        unit="", raw=raw, editable=False))
    elif afn_hex == "a1":
        if len(data) >= 2:
            if _is_fill(data[:2]):
                out.append(ElementValue(name="数据自报种类", value="-",
                                        unit="", raw=raw, editable=False))
            else:
                mask = data[0] | (data[1] << 8)
                names = [C.RT_KINDS_REPORT[i] for i in range(16) if (mask >> i) & 1]
                out.append(ElementValue(name="数据自报种类",
                                        value="、".join(names) or "无",
                                        unit="", raw=raw, editable=False))
            for i in range((len(data) - 2) // 2):
                iv = _safe_bcd_le(data[2 + i * 2:4 + i * 2])
                label = C.RT_KINDS_REPORT[i] if i < len(C.RT_KINDS_REPORT) else f"#{i}"
                out.append(ElementValue(name=f"自报间隔[{label}]",
                                        value=iv if iv is not None else "-",
                                        unit="min", raw=raw, editable=False))
            if warnings is not None and len(data) != 30:
                warnings.append(
                    f"AFN=A1H 数据域 {len(data)}B，规约固定 30B（14 个间隔），"
                    "按实际长度解析")
    elif afn_hex == "a2":
        out.append(ElementValue(name="主备信道配置", value=raw, unit="",
                                raw=raw, editable=False))
    return out


def _fmt_time_427(data: bytes) -> str:
    """Tp 时间标签（6.3.3.8）：前6B BCD(秒分时日月年) + 第7B BIN允许传输延时时长(min)。"""

    if _is_fill(data[:6]):
        return "-"
    fields = [safe_bcd_to_int(data[i]) for i in range(6)]
    if any(f is None for f in fields):
        return f"无效时间({bytes_to_hex_compact(data[:6])})"
    sec, min_val, hour, day, month, year = fields
    delay = data[6] if len(data) > 6 else 0
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23
            and min_val <= 59 and sec <= 59):
        return f"无效时间({bytes_to_hex_compact(data[:6])})"
    r = f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{min_val:02d}:{sec:02d}"
    if delay > 0:
        r += f" (传输延时限{delay}min)"
    return r

def _format_addr(addr: bytes) -> str:
    """格式化地址域 A（表7/表8）。

    方式1: A1=3B BCD(行政区划码) + A2=2B BIN(站址, 小端)
    方式2: BYTE1=00H + BYTE2~5=8位HEX监测站编码(nibble-packed)

    判定依据（规约 §6.3.3.4 表7/表8）：方式1 行政区划码 A1 为 6 位十进制，
    前两位为省码（GB/T2260 规定为 11~82），故 A1 首字节恒 ≥ 0x11，不可能为 00H。
    因此 BYTE1=00H 可靠判定为方式2，不存在方式1 被误判的边界。
    """

    if not addr:
        return "-"
    if all(b == 0xAA for b in addr) or all(b == 0xFF for b in addr):
        return "-"
    if addr[0] == 0x00:
        hex_code = ""
        for b in addr[1:]:
            hex_code += f"{b:02X}"  # nibble-packed HEX, zero-pad per byte
        return f"方式2 站点编码: {hex_code}"
    admin = bcd_bytes_to_int(bytes(addr[:3]))
    stn_id = int.from_bytes(bytes(addr[3:5]), "little")  # A2=2B BIN little-endian
    if stn_id <= 60000:
        label = "遥测站"
    elif stn_id <= 65534:
        label = "中继站"
    else:
        label = "广播地址"
    return f"方式1 行政区划:{admin} 站址:{stn_id} ({label})"


def _build_byte_map(bytes_list: list[int]) -> str:
    """构建逐字节映射视图。"""
    parts = []
    parts.append(bytes_to_hex(bytes(bytes_list[:3])))
    ctrl_len = 2 if ((bytes_list[3] >> 6) & 1) else 1
    parts.append(bytes_to_hex(bytes(bytes_list[3: 3 + ctrl_len])))
    parts.append(bytes_to_hex(bytes(bytes_list[3 + ctrl_len: 8 + ctrl_len])))
    parts.append(bytes_to_hex(bytes(bytes_list[8 + ctrl_len: 9 + ctrl_len])))
    if len(bytes_list) > 9 + ctrl_len + 2:
        parts.append(bytes_to_hex(bytes(bytes_list[9 + ctrl_len: -2])))
    parts.append(bytes_to_hex(bytes(bytes_list[-2: -1])))
    parts.append(bytes_to_hex(bytes(bytes_list[-1:])))
    return " ".join(parts)


class SL427Decoder:
    """SL427 报文解码器。"""

    #: 允许 DIV=1 重组的 AFN（无 AUX，且 L 语义按表3 字节）。
    #: 83/61 图片帧可能使用 §6.3.3.2b 的 L×1K 语义，未证前不重组。
    _DIV_REASSEMBLE_AFNS = frozenset({0xB0, 0xB1, 0x84})

    def __init__(self, allow_single_div: bool = False) -> None:
        # 单帧 DIVS=1 与「多帧末片」在协议层无法区分；默认不解析孤立 DIVS=1，
        # 避免前序分片丢失/坏 CRC 时把末片当完整报文（宁可少给，不可错给）。
        self.allow_single_div = allow_single_div
        self._buf = b""
        self._pending: dict[tuple, dict[int, bytes]] = {}
        self._pending_meta: dict[tuple, dict] = {}
        self._pending_max_groups = 64
        self._pending_max_bytes = 8 * 1024 * 1024
        self._pending_ttl = 300.0
        self._buf_max = 64 * 1024
        self.errors: list[str] = []
        self.dropped_frames = 0

    def _record_error(self, message: str) -> None:
        self.dropped_frames += 1
        if len(self.errors) >= 100:
            self.errors.pop(0)
        self.errors.append(message)

    def feed(self, data: bytes) -> list[DecodedMessage]:
        """流式输入 SL427 字节，返回本次可完整解析的报文。

        DIV=1 的分帧报文仅对 B0/B1/84 重组；C0/81/82/FF、83/61 走安全降级。
        坏帧/超限缓存写入 ``errors``，``dropped_frames`` 计数。
        """
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"feed() 需要 bytes，实际 {type(data).__name__}")
        self._buf += bytes(data)
        out: list[DecodedMessage] = []
        steps = 0
        while True:
            steps += 1
            if steps % 64 == 0:
                self._evict_pending()
            frame, consumed = self._extract_frame(self._buf)
            if consumed:
                self._buf = self._buf[consumed:]
            if frame is None:
                if consumed == 0:
                    if len(self._buf) > self._buf_max:
                        self._buf = self._buf[1:]
                        self._record_error("流式缓冲超过上限，丢弃 1 字节重同步")
                        continue
                    break
                continue
            try:
                if len(frame) < 10:
                    raise DecodeError(f"报文太短: {len(frame)} 字节")
                if crc8(frame[3:-2]) != frame[-2]:
                    raise DecodeError("CRC8 校验失败")
                ctrl = C.parse_ctrl(frame[3])
                if ctrl["div"] == 1:
                    if len(frame) < 11:
                        self._record_error(f"分帧帧长不足（{len(frame)}B），安全丢弃")
                        continue
                    afn = frame[10]
                    if afn in (0x61, 0x83):
                        # §6.3.3.2b 的 L×1K 语义未证，83/61 分帧一律安全丢弃
                        self._record_error(
                            f"AFN=0x{afn:02X} 图片分帧的 L×1K 语义未确认，安全丢弃")
                        continue
                    out.extend(self._handle_div_frame(frame, ctrl))
                else:
                    out.append(self.decode(frame))
            except DecodeError as e:
                self._record_error(f"丢弃 {len(frame)}B 无法解析帧: {e}")
                continue
        self._evict_pending()
        return out

    def reset(self) -> None:
        self._buf = b""
        self._pending.clear()
        self._pending_meta.clear()
        self.errors.clear()
        self.dropped_frames = 0

    def _extract_frame(self, buf: bytes) -> tuple[bytes | None, int]:
        """从缓冲提取一个 68 L 68 … CS 16 帧。"""
        n = len(buf)
        if n < 3:
            return None, 0
        i = 0
        while i + 2 < n:
            if buf[i] == C.START_BYTE and buf[i + 2] == C.START_BYTE:
                break
            i += 1
        else:
            return None, n
        if i > 0:
            return None, i
        if n < 3:
            return None, 0
        L = buf[1]
        if not 1 <= L <= 255:
            return None, 1
        total = L + 5
        if total > self._buf_max:
            return None, 1
        if n < total:
            # 谎报长度可能永久阻塞；若后方已有完整合法帧，跳到该帧重同步
            nxt = self._find_valid_start(buf, 1)
            if nxt is not None:
                return None, nxt
            return None, 0
        if buf[total - 1] != C.END_BYTE:
            nxt = self._find_valid_start(buf, 1)
            return None, (nxt if nxt is not None else 1)
        return buf[:total], total

    def _find_valid_start(self, buf: bytes, start: int) -> int | None:
        """寻找后方一个完整合法帧的起始位置（用于谎报长度重同步）。"""
        n = len(buf)
        for i in range(max(1, start), n - 5):
            if buf[i] != C.START_BYTE or buf[i + 2] != C.START_BYTE:
                continue
            L = buf[i + 1]
            total = L + 5
            if total >= 6 and i + total <= n and buf[i + total - 1] == C.END_BYTE:
                return i
        return None

    def _handle_div_frame(self, frame: bytes, ctrl: dict) -> list[DecodedMessage]:
        """缓存/组装 DIV=1 分帧；仅无 AUX 的 B0/B1/84 进入重组。"""
        divs = frame[4]
        afn = frame[10]
        if afn not in self._DIV_REASSEMBLE_AFNS:
            # C0/81/82/FF、83/61：安全降级，绝不把分片当完整报文
            return [self.decode(frame)]

        key = (ctrl["dir"], bytes(frame[5:10]), afn, ctrl["func_code"])
        now = time.monotonic()
        meta = self._pending_meta.get(key)
        if meta is not None and (now - meta["updated"] > self._pending_ttl):
            self._pending.pop(key, None)
            self._pending_meta.pop(key, None)
            meta = None
        if meta is None:
            meta = {"created": now, "updated": now, "warnings": []}
            self._pending_meta[key] = meta
        else:
            meta["updated"] = now
        group = self._pending.setdefault(key, {})

        if divs in group and group[divs] != frame:
            group.clear()
            meta["warnings"].append(f"DIVS={divs} 内容变化，重置该分帧组")
        group[divs] = frame
        if max(group) == 1 and not self.allow_single_div:
            if not any("孤立" in w for w in meta["warnings"]):
                meta["warnings"].append(
                    "孤立 DIVS=1 分片，等待其他分片确认（默认不按单帧解析）")

        # DIVS=1 可能先到（乱序），因此每次加入分片后都检查是否已可组装
        if 1 not in group:
            return []

        complete = all(i in group for i in range(1, max(group) + 1))
        if not complete:
            # 等待缺号分片；TTL/上限负责清理
            return []

        max_div = max(group)
        if max_div == 1 and not self.allow_single_div:
            return []  # 保留待确认；避免把多帧末片误当单帧
        frames = [group[i] for i in range(max_div, 0, -1)]
        group_warnings = list(meta["warnings"])
        del self._pending[key]
        del self._pending_meta[key]
        return [self._decode_div_reassembled(frames, ctrl, group_warnings)]

    def _decode_div_reassembled(
        self, frames: list[bytes], ctrl: dict, group_warnings: list[str]
    ) -> DecodedMessage:
        """直接把分片 D 送进解析管线，不再合成受 255B 限制的单帧。"""
        first = frames[0]
        addr_bytes = first[5:10]
        afn = first[10]
        payload = b"".join(f[11:-2] for f in frames)
        logical_ctrl = dict(ctrl)
        logical_ctrl["div"] = 0
        warnings: list[str] = []
        elements, special_info = self._parse_data_field(
            afn, logical_ctrl, payload, warnings, degrade=True)
        warnings.insert(
            0,
            f"多帧重组（{len(frames)} 片），各分片 CRC 已逐片校验；"
            "协议无报文标识，存在跨报文混组残余风险",
        )
        warnings.extend(group_warnings)
        direction = "上行（遥测站→中心站）" if logical_ctrl["dir"] else "下行（中心站→遥测站）"
        return DecodedMessage(
            hex_input="".join(bytes_to_hex_compact(f) for f in frames),
            direction=direction,
            ctrl_info=logical_ctrl,
            ctrl_func_name=C.CTRL_FUNC_MAP.get(
                logical_ctrl["func_code"], {}).get(
                    "name", f"未知(0x{logical_ctrl['func_code']:02X})"),
            addr_display=_format_addr(addr_bytes),
            afn=afn,
            afn_name=C.AFN_MAP.get(afn, f"未知(0x{afn:02X})"),
            data_len=len(payload),
            crc_calc=0,
            crc_recv=0,
            crc_ok=True,
            elements=elements,
            special_info=special_info,
            byte_map="",
            frame_length=sum(len(f) for f in frames),
            reassembled=True,
            packet_count=len(frames),
            warnings=warnings,
        )

    def _evict_pending(self) -> None:
        now = time.monotonic()
        for key, meta in list(self._pending_meta.items()):
            if now - meta["updated"] > self._pending_ttl:
                self._pending.pop(key, None)
                self._pending_meta.pop(key, None)
                detail = "；".join(meta.get("warnings", []))
                self._record_error("分帧组超时淘汰" + (f": {detail}" if detail else ""))

        def total_bytes() -> int:
            return sum(sum(len(v) for v in g.values()) for g in self._pending.values())

        while self._pending and (
            len(self._pending) > self._pending_max_groups
            or total_bytes() > self._pending_max_bytes
        ):
            oldest = min(self._pending_meta,
                         key=lambda k: (self._pending_meta[k]["created"],
                                        self._pending_meta[k]["updated"]))
            self._pending.pop(oldest, None)
            self._pending_meta.pop(oldest, None)
            self._record_error("分帧缓存超过组数/字节上限，淘汰最旧组")

    def decode_hex(self, hex_str: str) -> DecodedMessage:
        cleaned = "".join(hex_str.split())
        if not cleaned:
            raise DecodeError("报文为空")
        if any(c not in "0123456789ABCDEFabcdef" for c in cleaned):
            raise DecodeError("报文包含非十六进制字符")
        if len(cleaned) % 2 != 0:
            raise DecodeError("报文长度不是偶数")
        if not cleaned.lower().startswith("68"):
            raise DecodeError("报文不是以 68H 开头")
        return self.decode(bytes.fromhex(cleaned))

    def decode(self, frame: bytes) -> DecodedMessage:
        try:
            return self._decode_inner(frame)
        except DecodeError:
            raise
        except (ValueError, IndexError) as e:
            raise DecodeError(f"报文解析失败: {e}") from e

    def _decode_inner(self, frame: bytes) -> DecodedMessage:
        bytes_list = list(frame)
        total = len(bytes_list)

        if total < 10:
            raise DecodeError(f"报文太短: {total} 字节")

        if bytes_list[0] != C.START_BYTE or bytes_list[2] != C.START_BYTE:
            raise DecodeError("帧起始标识错误，期望 68H 68H")
        if bytes_list[-1] != C.END_BYTE:
            raise DecodeError(f"帧结束标识错误，期望 16H，实际 {bytes_list[-1]:02X}H")

        data_len = bytes_list[1]

        user_start = 3
        cs_pos = total - 2
        user_len_actual = cs_pos - user_start
        if user_len_actual < 0 or user_len_actual != data_len:
            raise DecodeError(f"L={data_len} 但用户区实际长度={user_len_actual}，不匹配")
        user_data = bytes(bytes_list[user_start: cs_pos])
        calc_crc = crc8(user_data)
        recv_crc = bytes_list[cs_pos]

        ctrl = C.parse_ctrl(bytes_list[3])
        # 最小 L 校验: C(1B+分帧扩展) + A(5B) + AFN(1B)
        min_l = 8 if ctrl["div"] == 1 else 7
        if data_len < min_l:
            raise DecodeError(f"L={data_len} 小于最小用户区长度 {min_l}（C+A+AFN）")
        ctrl_func_name = C.CTRL_FUNC_MAP.get(ctrl["func_code"], {}).get("name", f"未知(0x{ctrl['func_code']:02X})")

        direction = "上行（遥测站→中心站）" if ctrl["dir"] else "下行（中心站→遥测站）"

        offset = 4
        if ctrl["div"] == 1:
            offset += 1

        addr_bytes = bytes(bytes_list[offset: offset + 5])
        offset += 5
        afn = bytes_list[offset]
        offset += 1
        afn_name = C.AFN_MAP.get(afn, f"未知(0x{afn:02X})")

        data_field = bytes(bytes_list[offset: cs_pos])
        addr_display = _format_addr(addr_bytes)
        divs = bytes_list[4] if ctrl["div"] == 1 else None

        warnings: list[str] = []
        if ctrl["div"] == 1:
            # 单帧 decode() 无法知道其余分片；绝不能把分片当完整报文解析。
            warnings.append(
                f"分帧报文（DIV=1, DIVS=0x{divs:02X}）需多帧重组；"
                "单帧解码不解析数据域，请使用 feed() 或提供完整分片"
            )
            elements: list[ElementValue] = []
            special_info = None
        else:
            elements, special_info = self._parse_data_field(
                afn, ctrl, data_field, warnings
            )

        byte_map = _build_byte_map(bytes_list)

        return DecodedMessage(
            hex_input=bytes_to_hex_compact(frame),
            direction=direction,
            ctrl_info=ctrl,
            ctrl_func_name=ctrl_func_name,
            addr_display=addr_display,
            afn=afn,
            afn_name=afn_name,
            data_len=data_len,
            crc_calc=calc_crc,
            crc_recv=recv_crc,
            crc_ok=calc_crc == recv_crc,
            elements=elements,
            special_info=special_info,
            byte_map=byte_map,
            frame_length=total,
            warnings=warnings,
        )

    @staticmethod
    def _raw_param_element(name: str, data: bytes) -> ElementValue:
        return ElementValue(
            name=name, value=bytes_to_hex_compact(data) or "-",
            unit="", raw=bytes_to_hex_compact(data), editable=False,
        )

    def _parse_0d_payload(
        self, afn_hex: str, real_data: bytes,
        elements: list[ElementValue], warnings: list[str],
    ) -> None:
        """0x0D 上下文分派（表24 D12 / §7.3.22 n) / §7.5.5 / §7.5.2b）。

        - B0（§7.3.22 n）、84（§7.5.5）、C0/82（表24 D12 的终端电压子类）：
          D=2B 电压；D=0 时无参数；其他长度写原始摘要 + warning。
        - 81（§7.5.2b）：0x0D 属「其他参数」，无中间参数；D 非空写原始摘要 + warning。
        - C0+0x0D 的布局规约未明文定义（§7.5.6 自报条件不含电压），
          按 §7.3.22 n 的 2B 电压格式作最一致解读，非 2B 一律可观测降级。
        """
        if not real_data:
            return
        if afn_hex in ("b0", "c0", "82"):
            if len(real_data) == 2:
                elements.extend(_parse_ctrl_func_data(0x0D, real_data))
            else:
                warnings.append(
                    f"AFN={afn_hex.upper()}H func=0x0D 的 D 为 {len(real_data)} 字节"
                    "（应为 2B 电压），已降级为原始摘要"
                )
                elements.append(self._raw_param_element("0x0D 参数原始数据", real_data))
        else:  # 81
            warnings.append(
                f"AFN={afn_hex.upper()}H func=0x0D 不应携带中间参数，"
                f"收到 {len(real_data)} 字节，已降级为原始摘要"
            )
            elements.append(self._raw_param_element("0x0D 参数原始数据", real_data))

    def _parse_data_field(
        self, afn: int, ctrl: dict, data_field: bytes,
        warnings: list[str] | None = None,
        *, degrade: bool = False,
    ) -> tuple[list[ElementValue], dict | None]:
        """统一受保护的数据域解析入口；degrade=True 用于分帧重组降级。"""
        if warnings is None:
            warnings = []
        try:
            return self._parse_data_field_impl(afn, ctrl, data_field, warnings)
        except DecodeError:
            raise
        except (ValueError, IndexError) as e:
            if not degrade:
                raise DecodeError(f"数据域解析失败: {e}") from e
            warnings.append(f"数据域解析失败，降级为原始摘要: {e}")
            return [self._raw_param_element("重组原始数据", data_field)], None

    def _parse_b1_records(
        self, func_code: int, rest: bytes, warnings: list[str],
        param_byte: int | None = None,
    ) -> list[ElementValue]:
        """按 func_code 展开 B1 存储记录；返回已解析要素，余字节留 warning。

        统一走 `_parse_parameter_records` 的 consumed 对账：0x03 按流量+累计水量
        成对（10B）、0x07 按 8B、0x0A 按 B1 单参数 4B、0x0B 按 4B，其余按 byteLen。
        """
        if func_code == 0x0E:
            items = _parse_statistical_rainfall(rest)
            consumed = len(items) * 4
        else:
            definition = C.CTRL_FUNC_MAP.get(func_code)
            if not definition or definition["byteLen"] <= 0:
                return []
            items = []
            consumed = 0
            while consumed < len(rest):
                parsed, used = _parse_parameter_records(
                    func_code, rest[consumed:], context="b1",
                    warnings=warnings, max_records=1,
                    param_byte=param_byte)
                if used == 0:
                    break
                items.extend(parsed)
                consumed += used
        if items and consumed < len(rest):
            warnings.append(
                f"AFN=B1H 存储数据 {len(rest)}B，已解析 {consumed}B，"
                f"剩余 {len(rest) - consumed}B 未展开")
        return items

    def _parse_data_field_impl(
        self, afn: int, ctrl: dict, data_field: bytes,
        warnings: list[str] | None = None,
    ) -> tuple[list[ElementValue], dict | None]:
        if warnings is None:
            warnings = []
        elements = []
        special_info = None
        is_downlink = not ctrl["dir"]

        if is_downlink:
            afn_label = C.AFN_MAP.get(afn, f"未知(0x{afn:02X})")
            func_label = C.CTRL_FUNC_MAP.get(ctrl["func_code"], {}).get("name", "未知")
            elements.append(ElementValue(
                name="下行报文", value=f"AFN=0x{afn:02X}({afn_label}) 功能=({func_label})",
                unit="", raw=bytes_to_hex_compact(data_field), editable=False,
            ))
            return elements, special_info

        afn_hex = f"{afn:02x}".lower()
        func_code = ctrl["func_code"]

        if afn_hex == "02":
            if len(data_field) == 0:
                special_info = {"type": "heart", "code": 0, "name": "空数据"}
            else:
                hc = data_field[0]
                hn = C.HEART_MAP.get(hc, f"未知(0x{hc:02X})")
                special_info = {"type": "heart", "code": hc, "name": hn}
                elements.append(ElementValue(
                    name="心跳类型", value=hn,
                    unit="", raw=f"{hc:02X}", editable=False,
                ))

        elif afn_hex == "c0":
            # 自报实时数据: D + alarm(2B) + state(2B) + Tp(7B)
            raw_len = len(data_field)
            if raw_len >= C.TP_LEN + 4:
                tp_bytes = data_field[-C.TP_LEN:]
                state_bytes = data_field[-C.TP_LEN - 2:-C.TP_LEN]
                alarm_bytes = data_field[-C.TP_LEN - 4:-C.TP_LEN - 2]
                real_data = data_field[:-C.TP_LEN - 4]
                if func_code == 0x0D:
                    # 81 无中间参数（§7.5.2b）；82 与 C0 同为 2B 电压（表24 D12）
                    self._parse_0d_payload(afn_hex, real_data, elements, warnings)
                elif len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_statistical_rainfall(real_data))
                    else:
                        _extend_parameter_records(
                            elements, func_code, real_data,
                            context="c0", warnings=warnings)
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
                tp_str = _fmt_time_427(tp_bytes)
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(tp_bytes),
                    is_time=True, byte_len=C.TP_LEN,
                ))
            else:
                # 数据域不足 D+alarm+state+Tp，降级按功能码解析现有数据
                missing = "Tp" if raw_len >= 4 else "alarm/state/Tp"
                warnings.append(
                    f"AFN=C0 数据域仅 {raw_len} 字节（<{C.TP_LEN + 4}），"
                    f"缺少 {missing}，按现有数据降级解析"
                )
                if func_code == 0x0E:
                    elements.extend(_parse_statistical_rainfall(data_field))
                elif func_code == 0x0D:
                    if len(data_field) >= 4:
                        elements.extend(_parse_alarm(data_field[:2]))
                        elements.extend(_parse_terminal(data_field[2:4]))
                    elif data_field:
                        elements.append(self._raw_param_element("0x0D 参数原始数据", data_field))
                else:
                    _extend_parameter_records(
                        elements, func_code, data_field,
                        context="c0", warnings=warnings)

        elif afn_hex == "b0":
            # 查询响应：data + alarm(2B) + state(2B)（规范7.3.22）
            raw_len = len(data_field)
            if raw_len >= 4:
                state_bytes = data_field[-2:]
                alarm_bytes = data_field[-4:-2]
                real_data = data_field[:-4]
                if func_code == 0x0D:
                    self._parse_0d_payload("b0", real_data, elements, warnings)
                elif len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_comprehensive(real_data, warnings))
                    else:
                        _extend_parameter_records(
                            elements, func_code, real_data,
                            context="b0", warnings=warnings)
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
            else:
                if func_code == 0x0E:
                    elements.extend(_parse_comprehensive(data_field, warnings))
                else:
                    _extend_parameter_records(
                        elements, func_code, data_field,
                        context="b0", warnings=warnings)

        elif afn_hex in ("61", "83"):
            special_info = {"type": "image", "bytes": data_field}
            elements.append(ElementValue(
                name="图像数据", value=f"{len(data_field)} 字节",
                unit="bytes", raw=bytes_to_hex_compact(data_field), editable=False,
            ))

        elif afn_hex in ("81", "82"):
            raw_len = len(data_field)
            if raw_len >= C.TP_LEN + 4:
                tp_bytes = data_field[-C.TP_LEN:]
                state_bytes = data_field[-C.TP_LEN - 2:-C.TP_LEN]
                if afn_hex == "81":
                    # 81H: alarm(2B) 在 data 之前（规范7.5.2）
                    alarm_bytes = data_field[:2]
                    real_data = data_field[2:-C.TP_LEN - 2]
                else:
                    # 82H: 同 C0，alarm(2B) 在 data 之后
                    alarm_bytes = data_field[-C.TP_LEN - 4:-C.TP_LEN - 2]
                    real_data = data_field[:-C.TP_LEN - 4]
                if func_code == 0x0D:
                    self._parse_0d_payload(afn_hex, real_data, elements, warnings)
                elif len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_statistical_rainfall(real_data))
                    else:
                        _extend_parameter_records(
                            elements, func_code, real_data,
                            context=afn_hex, warnings=warnings)
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
                tp_str = _fmt_time_427(tp_bytes)
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(tp_bytes),
                    is_time=True, byte_len=C.TP_LEN,
                ))
            else:
                missing = "Tp" if raw_len >= 4 else "alarm/state/Tp"
                warnings.append(
                    f"AFN={afn:02X}H 数据域仅 {raw_len} 字节（<{C.TP_LEN + 4}），"
                    f"缺少 {missing}，按现有数据降级解析"
                )
                if func_code == 0x0E:
                    elements.extend(_parse_statistical_rainfall(data_field))
                elif func_code == 0x0D:
                    if len(data_field) >= 4:
                        elements.extend(_parse_alarm(data_field[:2]))
                        elements.extend(_parse_terminal(data_field[2:4]))
                    elif data_field:
                        elements.append(self._raw_param_element("0x0D 参数原始数据", data_field))
                else:
                    _extend_parameter_records(
                        elements, func_code, data_field,
                        context="81", warnings=warnings)

        elif afn_hex == "b1":
            # 查询固态存储数据响应：前9B = 参数种类/编号 + 起止时间（表48），
            # 后续数据按控制域 func_code 分派 7.3.22 参数格式。
            if len(data_field) < 9:
                warnings.append(
                    f"AFN=B1H 数据域仅 {len(data_field)} 字节（<9），无法解析表48头")
                elements.append(self._raw_param_element("B1 原始数据", data_field))
            else:
                param = data_field[0]
                elements.append(ElementValue(
                    name="参数种类/编号",
                    value=f"0x{param:02X}（类别={(param >> 4) & 0x0F}, 编号={param & 0x0F}）",
                    unit="", raw=f"{param:02X}", editable=False,
                ))
                for label, seg in (("开始时间", data_field[1:5]),
                                   ("结束时间", data_field[5:9])):
                    hour = safe_bcd_to_int(seg[0])
                    day = safe_bcd_to_int(seg[1])
                    month = safe_bcd_to_int(seg[2])
                    year = safe_bcd_to_int(seg[3])
                    valid = not (None in (hour, day, month, year)
                                 or not 0 <= hour <= 23
                                 or not 1 <= month <= 12
                                 or not 1 <= day <= 31)
                    if valid:
                        try:
                            date(2000 + year, month, day)
                        except ValueError:
                            valid = False
                    if not valid:
                        text = "-"
                        warnings.append(
                            f"AFN=B1H {label}越界或非法: {bytes_to_hex_compact(seg)}")
                    else:
                        text = f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:00"
                    elements.append(ElementValue(
                        name=label, value=text, unit="",
                        raw=bytes_to_hex_compact(seg), editable=False, is_time=True,
                    ))
                rest = data_field[9:]
                if rest:
                    parsed = self._parse_b1_records(func_code, rest, warnings, param_byte=param)
                    if parsed:
                        elements.extend(parsed)
                    else:
                        warnings.append(
                            f"AFN=B1H func=0x{func_code:02X} 的存储数据无法按 7.3.22 解析，"
                            "降级为原始摘要")
                        elements.append(self._raw_param_element("B1 存储数据", rest))
                else:
                    warnings.append("AFN=B1H 仅含表48头，无存储数据")

        elif afn_hex == "84":
            # 自报电压: 规范表B.98 自报帧数据域仅 2B BCD 电压（低位在前），无 alarm/state/Tp
            if len(data_field) > 2:
                warnings.append(
                    f"AFN=84H 数据域 {len(data_field)} 字节（>2B），仅解析前 2B 电压")
            if len(data_field) >= 2:
                seg = data_field[:2]
                v = _safe_bcd_le(seg)
                if v is None:
                    warnings.append("AFN=84H 电压为 0xAA/0xFF 缺测填充，降级显示 '-'")
                    volt_val = "-"
                else:
                    volt_val = f"{v / 100:.2f}"
                elements.append(ElementValue(
                    name="电压", value=volt_val, unit="V",
                    raw=bytes_to_hex_compact(seg),
                    byte_len=2, decimal=2,
                ))
            else:
                warnings.append(
                    f"AFN=84H 数据域仅 {len(data_field)} 字节，不足 2B 电压，无法解析"
                )

        elif afn_hex in (
            "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
            "5a", "5c", "5d", "5e", "5f", "60", "62", "63", "64", "65",
        ):
            elements.extend(_parse_query_response(afn_hex, data_field, warnings))

        elif afn_hex in ("90", "91", "92", "93", "94", "95", "96", "a0", "a1", "a2"):
            elements.extend(_parse_control_response(afn_hex, data_field, warnings))

        elif afn_hex == "ff":
            # FFH 用户自定义扩展：按 AFN_TP_ONLY 声明含尾部 Tp(7B)，剥离后再解析数据域
            ff_data = data_field
            if len(data_field) > C.TP_LEN:
                tp_bytes = data_field[-C.TP_LEN:]
                ff_data = data_field[:-C.TP_LEN]
                tp_str = _fmt_time_427(tp_bytes)
            else:
                tp_str = ""
            if func_code == 0x0E:
                elements.extend(_parse_comprehensive(ff_data, warnings))
            else:
                _extend_parameter_records(
                    elements, func_code, ff_data,
                    context="ff", warnings=warnings)
            if tp_str:
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(data_field[-C.TP_LEN:]),
                    is_time=True, byte_len=C.TP_LEN,
                ))

        else:
            if 0x10 <= afn <= 0x4F and not is_downlink:
                if len(data_field) == 1:
                    cfm = data_field[0]
                    cfm_map = {0x5A: "确认成功", 0x06: "ACK", 0x15: "NAK"}
                    cfm_text = cfm_map.get(cfm, f"0x{cfm:02X}")
                    elements.append(ElementValue(
                        name=f"AFN=0x{afn:02X}确认响应",
                        value=cfm_text, unit="",
                        raw=bytes_to_hex_compact(data_field), editable=False,
                    ))
                else:
                    elements.append(ElementValue(
                        name=f"AFN=0x{afn:02X}响应",
                        value=bytes_to_hex_compact(data_field), unit="",
                        raw=bytes_to_hex_compact(data_field), editable=False,
                    ))
            else:
                elements.append(ElementValue(
                    name="未知功能码", value=f"AFN=0x{afn:02X}",
                    unit="", raw=bytes_to_hex_compact(data_field), editable=False,
                ))

        return elements, special_info


def decode_hex(hex_str: str) -> DecodedMessage:
    return SL427Decoder().decode_hex(hex_str)


def decode(frame: bytes) -> DecodedMessage:
    return SL427Decoder().decode(frame)
