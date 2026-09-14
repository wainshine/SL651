"""SL427-2021 水资源监测数据传输规约 解码器。

帧结构: 68 L 68 | C | A(5B) | AFN | data... | CS(CRC8) | 16
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sl651.bcd import (
    bcd_bytes_to_int,
    bcd_bytes_to_int_le,
    bytes_to_hex,
    bytes_to_hex_compact,
    safe_bcd_to_int,
)
from sl651.crc import crc8
from . import constants as C


class DecodeError(Exception):
    """解码异常。"""


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
            "warnings": list(self.warnings),
        }


def _parse_ctrl_func_data(func_code: int, data_bytes: bytes, max_items: int | None = None) -> list[ElementValue]:
    """解析控制功能码对应的数据。max_items 限制解析条数（综合参数用，每型仅一次）。"""
    definition = C.CTRL_FUNC_MAP.get(func_code)
    if not definition or definition["byteLen"] == 0:
        return []

    items = []
    pos = 0
    remaining = list(data_bytes)

    while pos < len(remaining):
        if max_items is not None and len(items) >= max_items:
            break
        item_len = definition["byteLen"]
        if pos + item_len > len(remaining):
            break
        chunk = bytes(remaining[pos: pos + item_len])
        pos += item_len
        hex_str = bytes_to_hex_compact(chunk)

        if all(b == 0xFF for b in chunk):
            if not definition["array"]:
                break
            continue

        if all(b == 0xAA for b in chunk):
            if not definition["array"]:
                break
            continue

        if func_code == 0x03:
            display, raw, unit_str = _parse_flow(chunk, definition["decimal"])
            items.append(ElementValue(
                name=definition["name"],
                value=display,
                unit=unit_str,
                raw=raw,
                byte_len=item_len,
                decimal=definition["decimal"],
                signed=definition["signed"],
            ))
        elif definition["signed"]:
            result = _parse_signed_bcd(chunk, definition["decimal"])
            result_unit = definition["unit"]
            items.append(ElementValue(
                name=definition["name"],
                value=result[0],
                unit=result_unit,
                raw=result[1],
                byte_len=item_len,
                decimal=definition["decimal"],
                signed=definition["signed"],
            ))
        else:
            v = bcd_bytes_to_int_le(chunk)
            result = (f"{v / (10 ** definition['decimal']):.{definition['decimal']}f}", hex_str)
            items.append(ElementValue(
                name=definition["name"],
                value=result[0],
                unit=definition["unit"],
                raw=result[1],
                byte_len=item_len,
                decimal=definition["decimal"],
                signed=definition["signed"],
            ))
        if not definition["array"]:
            break

    return items


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
    if all(b == 0xAA for b in data):
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


def _parse_comprehensive(data: bytes) -> list[ElementValue]:
    """解析综合参数（0x0E 功能码）。
    按规范表45，D0~D7 依次为水质/土壤含水率/功率/气象/闸位/流量/水位/雨量。
    """
    if len(data) == 0:
        return []
    bit_flag = data[0]
    remaining = list(data[1:])
    offset = 0
    items = []
    for i in range(len(C.COMP_BITS)):
        if bit_flag & (1 << i):
            func_code = C.COMP_BITS[i]
            definition = C.CTRL_FUNC_MAP.get(func_code)
            item_len = definition["byteLen"] if definition else 0
            chunk = bytes(remaining[offset:])
            sub_items = _parse_ctrl_func_data(func_code, chunk, max_items=1)
            items.extend(sub_items)
            # 该 bit 对应定长数据块，无论是否解析出值（全 0xFF/0xAA 填充时无值）都必须跳过
            offset += item_len
    return items


def _parse_statistical_rainfall(data: bytes) -> list[ElementValue]:
    """解析上行统计雨量（0x0E），规范7.5.6 c：1B 雨量类型 + 3B 雨量数据（小端 BCD）。"""
    items = []
    pos = 0
    rain_type_map = {0x00: "本次", 0x01: "小时", 0x02: "日", 0x03: "月", 0x04: "年"}
    while pos + 4 <= len(data):
        rtype = data[pos]
        rdata = data[pos + 1: pos + 4]
        pos += 4
        try:
            v = bcd_bytes_to_int_le(rdata)
            val = f"{v / 100:.2f}"
        except (ValueError, IndexError):
            val = "-"
        rtype_name = rain_type_map.get(rtype, f"类型0x{rtype:02X}")
        items.append(ElementValue(
            name=f"统计雨量({rtype_name})",
            value=val, unit="mm",
            raw=bytes_to_hex_compact(bytes([rtype]) + rdata),
            byte_len=4, decimal=2,
        ))
    return items


def _parse_alarm(data: bytes) -> list[ElementValue]:
    """解析告警状态。"""
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
    """解析终端状态。"""
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

def _bcd_le_signed(data: bytes) -> int:
    """小端 BCD（末字节 D7 为符号位，1=负）-> 有符号整数。"""
    if not data:
        return 0
    last = data[-1]
    neg = bool(last & 0x80)
    clean = bytes(data[:-1]) + bytes([last & 0x7F])
    try:
        v = bcd_bytes_to_int_le(clean)
    except ValueError:
        return 0
    return -v if neg else v


def _parse_flow_limit_427(seg: bytes) -> tuple[float, str]:
    """解析 5B 流量参数（表20，小端 BCD，BYTE5 高半字节=符号/单位）。"""
    if len(seg) < 5:
        return 0.0, ""
    high = seg[4]
    sign = -1 if (high & 0xC0) == 0xC0 else 1
    unit = "m³/h" if (high & 0x30) == 0x30 else "m³/s"
    scaled = bcd_bytes_to_int_le(seg[:4]) + (high & 0x0F) * 10 ** 8
    return sign * scaled / 1000.0, unit


def _parse_switch_record_427(seg: bytes) -> str:
    """解析 5B 中继切换时间（表32：分 时 日 星期月 年 BCD）。"""
    if len(seg) < 5:
        return bytes_to_hex_compact(seg)
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
    """解析 7B 水位基值/上下限（表15/16，小端 BCD，基值第3字节 D7 符号位）。"""
    if len(seg) < 7:
        return []
    b0, b1, b2 = seg[0], seg[1], seg[2]
    base_scaled = bcd_bytes_to_int_le(bytes([b0, b1, b2 & 0x7F]))
    base = base_scaled / 100.0
    if b2 & 0x80:
        base = -base
    lower = bcd_bytes_to_int_le(seg[3:5]) / 100.0
    upper = bcd_bytes_to_int_le(seg[5:7]) / 100.0
    return [
        ElementValue(name="水位基值", value=base, unit="m",
                     raw=bytes_to_hex_compact(seg[:3]), editable=False, decimal=2),
        ElementValue(name="水位下限", value=lower, unit="m",
                     raw=bytes_to_hex_compact(seg[3:5]), editable=False, decimal=2),
        ElementValue(name="水位上限", value=upper, unit="m",
                     raw=bytes_to_hex_compact(seg[5:7]), editable=False, decimal=2),
    ]


def _parse_pressure_limits_427(seg: bytes) -> list[ElementValue]:
    """解析 8B 水压上/下限（表17，4B 小端 BCD ×2）。"""
    if len(seg) < 8:
        return []
    upper = bcd_bytes_to_int_le(seg[:4]) / 100.0
    lower = bcd_bytes_to_int_le(seg[4:8]) / 100.0
    return [
        ElementValue(name="水压上限", value=upper, unit="kPa",
                     raw=bytes_to_hex_compact(seg[:4]), editable=False, decimal=2),
        ElementValue(name="水压下限", value=lower, unit="kPa",
                     raw=bytes_to_hex_compact(seg[4:8]), editable=False, decimal=2),
    ]


def _parse_water_quality_427(data: bytes) -> list[ElementValue]:
    """解析水质参数种类及上/下限（表18，5B 位图 + N×4B 小端 BCD）。"""
    out: list[ElementValue] = []
    if len(data) < 5:
        return out
    mask = int.from_bytes(data[:5], "little")
    body = data[5:]
    idx = 0
    for bit in range(40):
        if (mask >> bit) & 1:
            seg = body[idx * 4:idx * 4 + 4]
            if len(seg) < 4:
                break
            name = C.WATER_QUALITY_PARAMS[bit] if bit < len(C.WATER_QUALITY_PARAMS) else f"参数{bit}"
            out.append(ElementValue(name=name, value=bcd_bytes_to_int_le(seg),
                                    unit="", raw=bytes_to_hex_compact(seg),
                                    editable=False))
            idx += 1
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
        if t == 0xAA:
            out.append(ElementValue(name=label, value="无", unit="",
                                    raw="AA", editable=False))
            pos += 1  # 0xAAAA 两字节
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


def _parse_query_response(afn_hex: str, data: bytes) -> list[ElementValue]:
    """解析查询类响应帧（AFN=50H~65H，规约 7.3.2~7.3.21）。"""
    out: list[ElementValue] = []
    raw = bytes_to_hex_compact(data)

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
            name = {0: "兼容", 1: "自报", 2: "查询/应答", 3: "调试"}.get(mode, f"未知({mode})")
            out.append(ElementValue(name="工作模式", value=name, unit="",
                                    raw=f"{mode:02X}", editable=False))
    elif afn_hex == "53":
        if len(data) >= 2:
            mask = data[0] | (data[1] << 8)
            names = [C.RT_KINDS_REPORT[i] for i in range(16) if (mask >> i) & 1]
            out.append(ElementValue(name="数据自报种类",
                                    value="、".join(names) or "无",
                                    unit="", raw=raw, editable=False))
            for i in range((len(data) - 2) // 2):
                iv = bcd_bytes_to_int_le(data[2 + i * 2:4 + i * 2])
                label = C.RT_KINDS_REPORT[i] if i < len(C.RT_KINDS_REPORT) else f"#{i}"
                out.append(ElementValue(name=f"自报间隔[{label}]", value=iv,
                                        unit="min", raw=raw, editable=False))
        else:
            out.append(ElementValue(name="数据自报种类及间隔", value=f"{len(data)} 字节",
                                    unit="bytes", raw=raw, editable=False))
    elif afn_hex == "54":
        if len(data) >= 2:
            mask = data[0] | (data[1] << 8)
            names = [C.CTRL_FUNC_MAP.get(i, {}).get("name", f"0x{i:02X}")
                     for i in range(16) if (mask >> i) & 1]
            out.append(ElementValue(name="实时数据种类", value="、".join(names) or "无",
                                    unit="", raw=f"{mask:04X}", editable=False))
    elif afn_hex == "55":
        if len(data) >= 9:
            out.append(ElementValue(name="最近充值量", value=bcd_bytes_to_int_le(data[:4]),
                                    unit="m³", raw=bytes_to_hex_compact(data[:4]),
                                    editable=False))
            out.append(ElementValue(name="剩余水量", value=_bcd_le_signed(data[4:9]),
                                    unit="m³", raw=bytes_to_hex_compact(data[4:9]),
                                    editable=False))
    elif afn_hex == "56":
        if len(data) >= 8:
            out.append(ElementValue(name="剩余水量报警值", value=bcd_bytes_to_int_le(data[:3]),
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
                out.append(ElementValue(name=lab, value=int.from_bytes(seg, "little"),
                                        unit=unit, raw=bytes_to_hex_compact(seg),
                                        editable=False))
    elif afn_hex == "60":
        if data:
            out.append(ElementValue(name="中继引导码长值", value=data[0], unit="s",
                                    raw=f"{data[0]:02X}", editable=False))
    elif afn_hex == "62":
        n = len(data) // 5
        for i in range(n):
            seg = data[i * 5:i * 5 + 5]
            out.append(ElementValue(name=f"转发站地址[{i + 1}]", value=_format_addr(seg),
                                    unit="", raw=bytes_to_hex_compact(seg),
                                    editable=False))
    elif afn_hex == "5d":
        n = min(len(data) // 2, len(C.EVENT_RECORDS))
        for i in range(n):
            seg = data[i * 2:i * 2 + 2]
            cnt = int.from_bytes(seg, "little")
            out.append(ElementValue(name=f"事件记录[{C.EVENT_RECORDS[i]}]", value=cnt,
                                    unit="次", raw=bytes_to_hex_compact(seg),
                                    editable=False))
    elif afn_hex == "57":
        # N×7B 水位基值/上下限 + 4B 终端机报警状态
        if len(data) >= 4:
            body, tail = data[:-4], data[-4:]
            for i in range(len(body) // 7):
                for e in _parse_level_limits_427(body[i * 7:i * 7 + 7]):
                    e.name = f"{e.name}[{i + 1}]"
                    out.append(e)
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
            out.extend(_parse_alarm(tail[:2]))
            out.extend(_parse_terminal(tail[2:4]))
    elif afn_hex in ("59", "5a"):
        out.extend(_parse_water_quality_427(data))
    elif afn_hex == "65":
        out.extend(_parse_channel_427(data))
    elif afn_hex == "63":
        if len(data) >= 2:
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
            out.extend(_parse_alarm(tail[:2]))
            out.extend(_parse_terminal(tail[2:4]))
    else:
        out.append(ElementValue(name="查询响应数据", value=f"{len(data)} 字节",
                                unit="bytes", raw=raw, editable=False))
    return out


def _parse_control_response(afn_hex: str, data: bytes) -> list[ElementValue]:
    """解析控制命令响应帧（AFN=90H~96H，规约 7.4）与配置响应（A0H~A2H）。"""
    out: list[ElementValue] = []
    raw = bytes_to_hex_compact(data)

    if afn_hex == "90":
        if data:
            txt = "执行完毕" if data[0] == 0x5A else f"0x{data[0]:02X}"
            out.append(ElementValue(name="复位响应", value=txt, unit="", raw=raw,
                                    editable=False))
    elif afn_hex == "91":
        if data:
            names = [n for bit, n in ((0, "雨量"), (1, "水位"), (2, "水量"))
                     if (data[0] >> bit) & 1]
            out.append(ElementValue(name="清空历史数据", value="、".join(names) or "无",
                                    unit="", raw=raw, editable=False))
    elif afn_hex in ("92", "93"):
        if data:
            code = data[0] & 0x0F
            is_valve = ((data[0] >> 4) & 0x0F) == 0x0F
            done = ((data[0] >> 4) & 0x0F) == 0x0A
            kind = "阀门/闸门" if is_valve else "水泵"
            act = "启动" if afn_hex == "92" else "关闭"
            txt = f"{kind}编号{code}" + (" 执行完毕" if done else "")
            out.append(ElementValue(name=f"{act}响应", value=txt, unit="", raw=raw,
                                    editable=False))
    elif afn_hex in ("94", "95"):
        if data:
            low = data[0] & 0x0F
            m = "A机" if low == 0x09 else ("B机" if low == 0x06 else f"0x{low:02X}")
            out.append(ElementValue(name="切换响应", value=m, unit="", raw=raw,
                                    editable=False))
    elif afn_hex == "96":
        if len(data) >= 2:
            out.append(ElementValue(name="密码设置响应",
                                    value=bcd_bytes_to_int_le(data[:2]),
                                    unit="", raw=raw, editable=False))
    elif afn_hex == "a0":
        if len(data) >= 2:
            mask = data[0] | (data[1] << 8)
            names = [C.RT_KINDS_QUERY[i] for i in range(16) if (mask >> i) & 1]
            out.append(ElementValue(name="需查询的实时数据种类",
                                    value="、".join(names) or "无",
                                    unit="", raw=raw, editable=False))
    elif afn_hex == "a1":
        if len(data) >= 2:
            mask = data[0] | (data[1] << 8)
            names = [C.RT_KINDS_REPORT[i] for i in range(16) if (mask >> i) & 1]
            out.append(ElementValue(name="数据自报种类",
                                    value="、".join(names) or "无",
                                    unit="", raw=raw, editable=False))
            for i in range((len(data) - 2) // 2):
                iv = bcd_bytes_to_int_le(data[2 + i * 2:4 + i * 2])
                label = C.RT_KINDS_REPORT[i] if i < len(C.RT_KINDS_REPORT) else f"#{i}"
                out.append(ElementValue(name=f"自报间隔[{label}]", value=iv,
                                        unit="min", raw=raw, editable=False))
    elif afn_hex == "a2":
        out.append(ElementValue(name="主备信道配置", value=raw, unit="",
                                raw=raw, editable=False))
    return out


def _fmt_time_427(data: bytes) -> str:
    """Tp 时间标签（6.3.3.8）：前6B BCD(秒分时日月年) + 第7B BIN允许传输延时时长(min)。"""

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

        self._warnings = []
        elements, special_info = self._parse_data_field(
            afn, ctrl, data_field
        )
        warnings = self._warnings

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

    def _parse_data_field(
        self, afn: int, ctrl: dict, data_field: bytes
    ) -> tuple[list[ElementValue], dict | None]:
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
                if len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_statistical_rainfall(real_data))
                    else:
                        elements.extend(_parse_ctrl_func_data(func_code, real_data))
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
                self._warnings.append(
                    f"AFN=C0 数据域仅 {raw_len} 字节（<{C.TP_LEN + 4}），"
                    "缺少 alarm/state/Tp，按现有数据降级解析"
                )
                if func_code == 0x0E:
                    elements.extend(_parse_statistical_rainfall(data_field))
                else:
                    elements.extend(_parse_ctrl_func_data(func_code, data_field))

        elif afn_hex == "b0":
            # 查询响应：data + alarm(2B) + state(2B)（规范7.3.22）
            raw_len = len(data_field)
            if raw_len >= 4:
                state_bytes = data_field[-2:]
                alarm_bytes = data_field[-4:-2]
                real_data = data_field[:-4]
                if len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_comprehensive(real_data))
                    else:
                        elements.extend(_parse_ctrl_func_data(func_code, real_data))
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
            else:
                if func_code == 0x0E:
                    elements.extend(_parse_comprehensive(data_field))
                else:
                    elements.extend(_parse_ctrl_func_data(func_code, data_field))

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
                if len(real_data) > 0:
                    if func_code == 0x0E:
                        elements.extend(_parse_statistical_rainfall(real_data))
                    else:
                        elements.extend(_parse_ctrl_func_data(func_code, real_data))
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
                tp_str = _fmt_time_427(tp_bytes)
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(tp_bytes),
                    is_time=True, byte_len=C.TP_LEN,
                ))
            else:
                self._warnings.append(
                    f"AFN={afn:02X}H 数据域仅 {raw_len} 字节（<{C.TP_LEN + 4}），"
                    "缺少 alarm/state/Tp，按现有数据降级解析"
                )
                if func_code == 0x0E:
                    elements.extend(_parse_statistical_rainfall(data_field))
                else:
                    elements.extend(_parse_ctrl_func_data(func_code, data_field))

        elif afn_hex == "84":
            # 自报电压: 规范表B.98 自报帧数据域仅 2B BCD 电压（低位在前），无 alarm/state/Tp
            if len(data_field) >= 2:
                volt_val = bcd_bytes_to_int_le(data_field[:2]) / 100
                elements.append(ElementValue(
                    name="电压", value=f"{volt_val:.2f}", unit="V",
                    raw=bytes_to_hex_compact(data_field[:2]),
                    byte_len=2, decimal=2,
                ))
            else:
                self._warnings.append(
                    f"AFN=84H 数据域仅 {len(data_field)} 字节，不足 2B 电压，无法解析"
                )

        elif afn_hex in (
            "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
            "5a", "5c", "5d", "5e", "5f", "60", "62", "63", "64", "65",
        ):
            elements.extend(_parse_query_response(afn_hex, data_field))

        elif afn_hex in ("90", "91", "92", "93", "94", "95", "96", "a0", "a1", "a2"):
            elements.extend(_parse_control_response(afn_hex, data_field))

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
                elements.extend(_parse_comprehensive(ff_data))
            else:
                elements.extend(_parse_ctrl_func_data(func_code, ff_data))
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
