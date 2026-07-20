"""SL427-2021 水资源监测数据传输规约 解码器。

帧结构: 68 L 68 | C | A(5B) | AFN | data... | CS(CRC8) | 16
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
        }


def _parse_ctrl_func_data(func_code: int, data_bytes: bytes) -> list[ElementValue]:
    """解析控制功能码对应的数据。"""
    definition = C.CTRL_FUNC_MAP.get(func_code)
    if not definition or definition["byteLen"] == 0:
        return []

    items = []
    pos = 0
    remaining = list(data_bytes)

    while pos < len(remaining):
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
    """解析有符号 BCD 值（小端）。"""
    last = data[-1]
    neg = ((last >> 4) & 0x0F) == 0x0F
    mod = bytearray(data)
    mod[-1] = last & 0x0F
    v = bcd_bytes_to_int_le(bytes(mod))
    d = 10 ** decimal
    r = (-1 if neg else 1) * v / d
    return (f"{r:.{decimal}f}", bytes_to_hex_compact(data))


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
            chunk = bytes(remaining[offset:])
            sub_items = _parse_ctrl_func_data(func_code, chunk)
            items.extend(sub_items)
            consumed = sum(e.byte_len for e in sub_items)
            offset += consumed
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

def _fmt_time_427(data: bytes) -> str:
    """Tp 时间标签（6.3.3.8）：前6B BCD(秒分时日月年) + 第7B BIN允许传输延时时长(min)。"""

    sec = safe_bcd_to_int(data[0]) or 0
    min_val = safe_bcd_to_int(data[1]) or 0
    hour = safe_bcd_to_int(data[2]) or 0
    day = safe_bcd_to_int(data[3]) or 0
    month = safe_bcd_to_int(data[4]) or 0
    year = safe_bcd_to_int(data[5]) or 0
    delay = data[6] if len(data) > 6 else 0
    r = f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{min_val:02d}:{sec:02d}"
    if delay > 0:
        r += f" (传输延时限{delay}min)"
    return r

def _format_addr(addr: bytes) -> str:
    """格式化地址域 A（表7/表8）。

    方式1: A1=3B BCD(行政区划码) + A2=2B BIN(站址, 小端)
    方式2: BYTE1=00H + BYTE2~5=8位HEX监测站编码(nibble-packed)
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

        elements, special_info = self._parse_data_field(
            afn, ctrl, data_field
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
                    elements.extend(_parse_ctrl_func_data(func_code, real_data))
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
                tp_str = _fmt_time_427(tp_bytes)
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(tp_bytes),
                    is_time=True, byte_len=C.TP_LEN,
                ))

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
                elements.extend(_parse_ctrl_func_data(func_code, data_field))

        elif afn_hex == "84":
            raw_len = len(data_field)
            if raw_len >= C.TP_LEN + 4 and len(data_field) >= 2:
                tp_bytes = data_field[-C.TP_LEN:]
                state_bytes = data_field[-C.TP_LEN - 2:-C.TP_LEN]
                alarm_bytes = data_field[-C.TP_LEN - 4:-C.TP_LEN - 2]
                volt_bytes = data_field[:-C.TP_LEN - 4]
                if volt_bytes:
                    volt_val = bcd_bytes_to_int_le(volt_bytes) / 100
                    elements.append(ElementValue(
                        name="电压", value=f"{volt_val:.2f}", unit="V",
                        raw=bytes_to_hex_compact(volt_bytes),
                        byte_len=len(volt_bytes), decimal=2,
                    ))
                elements.extend(_parse_alarm(alarm_bytes))
                elements.extend(_parse_terminal(state_bytes))
                tp_str = _fmt_time_427(tp_bytes)
                elements.append(ElementValue(
                    name="观测时间", value=tp_str, unit="",
                    raw=bytes_to_hex_compact(tp_bytes),
                    is_time=True, byte_len=C.TP_LEN,
                ))
            else:
                if len(data_field) >= 2:
                    volt_val = bcd_bytes_to_int_le(data_field[:2]) / 100
                    elements.append(ElementValue(
                        name="电压", value=f"{volt_val:.2f}", unit="V",
                        raw=bytes_to_hex_compact(data_field[:2]),
                        byte_len=2, decimal=2,
                    ))

        elif afn_hex == "ff":
            if func_code == 0x0E:
                elements.extend(_parse_comprehensive(data_field))
            else:
                elements.extend(_parse_ctrl_func_data(func_code, data_field))

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
