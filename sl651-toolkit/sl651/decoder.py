"""SL651-2014 报文解码器（基于 njnrs 实现重构）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import constants as C
from .bcd import (
    bcd_bytes_to_int,
    bytes_to_hex,
    bytes_to_hex_compact,
    safe_bcd_to_int,
)
from .crc import crc16


@dataclass
class ElementValue:
    """单个要素解析结果。"""
    code: str
    name: str
    value: Any
    unit: str
    raw: str
    data_type: str = "BCD"
    byte_len: int = 0
    decimal: int = 0
    is_sub: bool = False

    @property
    def display_value(self) -> str:
        if isinstance(self.value, (int, float)):
            return f"{self.value:.{self.decimal}f} {self.unit}".strip()
        return f"{self.value} {self.unit}".strip()


@dataclass
class DecodedMessage:
    """SL651 报文解析结果。"""
    hex_input: str = ""
    center_addr: str = ""
    station_addr: str = ""
    password: str = ""
    function_code: int = 0
    function_name: str = ""
    direction: int = 0
    direction_label: str = ""
    body_length: int = 0
    serial: str = ""
    tx_time: str = ""
    tx_time_display: str = ""
    station_type: str = ""
    station_type_name: str = ""
    obs_time: str = ""
    obs_time_display: str = ""
    is_uniform: bool = False
    encoding: str = "BCD"
    crc_received: int = 0
    crc_calculated: int = 0
    crc_ok: bool = True
    elements: list[ElementValue] = field(default_factory=list)
    byte_map: str = ""
    byte_table: list[dict] = field(default_factory=list)
    raw_frame: bytes = b""
    frame_length: int = 0
    message_type: str = ""  # 从功能码推导的报文类型，如 "定时报"、"加报报"

    def to_dict(self) -> dict:
        return {
            "center_addr": self.center_addr,
            "station_addr": self.station_addr,
            "password": self.password,
            "function_code": f"0x{self.function_code:02X}",
            "function_name": self.function_name,
            "message_type": self.message_type,
            "direction": self.direction_label,
            "body_length": self.body_length,
            "serial": self.serial,
            "tx_time": self.tx_time_display,
            "station_type": self.station_type_name,
            "obs_time": self.obs_time_display,
            "encoding": self.encoding,
            "crc_ok": self.crc_ok,
            "crc_received": f"0x{self.crc_received:04X}",
            "crc_calculated": f"0x{self.crc_calculated:04X}",
            "elements": [
                {"code": el.code, "name": el.name, "value": el.display_value,
                 "unit": el.unit, "raw": el.raw, "data_type": el.data_type}
                for el in self.elements
            ],
            "frame_length": self.frame_length,
        }


class DecodeError(Exception):
    """解码异常。"""


def _fmt_bcd_time_sec(hex_str: str) -> str:
    try:
        v = bcd_bytes_to_int(bytes.fromhex(hex_str))
        s = f"{v:012d}"
        return f"20{s[0:2]}-{s[2:4]}-{s[4:6]} {s[6:8]}:{s[8:10]}:{s[10:12]}"
    except (ValueError, IndexError):
        return hex_str


def _fmt_bcd_time_nosec(hex_str: str) -> str:
    try:
        v = bcd_bytes_to_int(bytes.fromhex(hex_str))
        s = f"{v:010d}"
        return f"20{s[0:2]}-{s[2:4]}-{s[4:6]} {s[6:8]}:{s[8:10]}"
    except (ValueError, IndexError):
        return hex_str


def _safe_bcd_val(hex_str: str, decimals: int, neg: bool) -> tuple[str, str]:
    """安全 BCD 解码，无效数据返回 '-'。负数时剥离 0xFF 前缀。"""
    c = hex_str.upper()
    if all(ch == "F" for ch in c) or (not c):
        return ("-", c)
    if neg:
        c = c[2:]  # strip FF prefix
    if not c:
        return ("-", c)
    try:
        v = bcd_bytes_to_int(bytes.fromhex(c))
    except ValueError:
        return ("-", c)
    d = 10 ** decimals
    r = (-1 if neg else 1) * v / d
    return (f"{r:.{decimals}f}", hex_str.upper())


def _safe_hex_val(hex_str: str, decimals: int, neg: bool) -> tuple[str, str]:
    """安全 HEX 解码。"""
    c = hex_str.upper()
    if all(ch == "F" for ch in c) or (not c):
        return ("-", c)
    if neg:
        c = c[2:]
    if not c:
        return ("-", c)
    try:
        v = int(c, 16)
    except ValueError:
        return ("-", c)
    d = 10 ** decimals
    r = (-1 if neg else 1) * v / d
    return (f"{r:.{decimals}f}", hex_str.upper())


def _build_byte_map(bytes_list: list[int], direction: int, etx_pos: int) -> str:
    lines = []
    for offset in range(0, len(bytes_list), 16):
        chunk = bytes_list[offset: offset + 16]
        parts = []
        for i, b in enumerate(chunk):
            h = f"{b:02X}"
            idx = offset + i
            if offset == 0 and i < 2:
                h = f"*{h}*"
            elif offset == 2 and i == 0:
                h = f"[{h}]"
            elif offset == 13 and i == 0:
                h = f"<{h}>"
            elif idx == etx_pos:
                h = f"<{h}>"
            elif idx > etx_pos:
                h = f"*{h}*"
            elif direction == 0 and 22 <= offset <= 23 and idx < 24:
                h = f"<{h}>"
            elif direction == 0 and 30 <= offset <= 31 and idx < 32:
                h = f"<{h}>"
            parts.append(h)
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _build_byte_table(bytes_list: list[int], direction: int, etx_pos: int) -> list[dict]:
    fields = [
        (0, 1, "帧起始符 7E7E"),
    ]
    if direction == 0:
        fields += [
            (2, 2, "中心站址"),
            (3, 7, "遥测站地址(5字节)"),
            (8, 9, "密码"),
            (10, 10, "功能码"),
            (11, 12, "报文标识(方向+长度)"),
            (13, 13, "STX(02)"),
            (14, 15, "流水号"),
            (16, 21, "发报时间(BCD 6B)"),
            (22, 23, "站码标识 F1F1"),
            (24, 28, "站码(5字节)"),
            (29, 29, "测站类别"),
            (30, 31, "观测时间标识 F0F0"),
            (32, 36, "观测时间(BCD 5B)"),
            (37, etx_pos - 1, "水文要素数据"),
        ]
    else:
        fields += [
            (2, 6, "遥测站地址(5字节)"),
            (7, 7, "中心站址"),
            (8, 9, "密码"),
            (10, 10, "功能码"),
            (11, 12, "报文标识"),
            (13, 13, "STX(02)"),
            (14, 15, "流水号"),
            (16, 21, "发报时间(BCD 6B)"),
            (22, etx_pos - 1, "响应数据"),
        ]
    fields.append((etx_pos, etx_pos, f"ETX({bytes_list[etx_pos]:02X})"))
    fields.append((etx_pos + 1, etx_pos + 2, "CRC16"))
    result = []
    for s, e, name in fields:
        s = min(s, len(bytes_list) - 1)
        e = min(e, len(bytes_list) - 1)
        if s > e:
            continue
        result.append({
            "offset": f"{s:02X}-{e:02X}",
            "hex": bytes_to_hex(bytes(bytes_list[s: e + 1])),
            "field": name,
        })
    return result


class SL651Decoder:
    """SL651 报文解码器。"""

    def decode_hex(self, hex_str: str) -> DecodedMessage:
        cleaned = "".join(hex_str.split())
        if not cleaned:
            raise DecodeError("报文为空")
        if any(c not in "0123456789ABCDEFabcdef" for c in cleaned):
            raise DecodeError("报文包含非十六进制字符")
        if len(cleaned) % 2 != 0:
            raise DecodeError("报文长度不是偶数")
        if cleaned[:4].upper() not in ("7E7E", "0101"):
            raise DecodeError("报文不是以 7E7E(HEX/BCD) 或 0101(ASCII) 开头")
        return self.decode(bytes.fromhex(cleaned))

    def decode(self, frame: bytes) -> DecodedMessage:
        if len(frame) < C.BODY_OFFSET + 4:
            raise DecodeError(f"报文太短: {len(frame)} 字节")

        bytes_list = list(frame)
        total = len(bytes_list)
        is_ascii = frame[0] == C.SOH
        ident_hi = bytes_list[11]
        ident_lo = bytes_list[12]
        direction = (ident_hi >> 7) & 1
        body_len = ((ident_hi & 0x7F) << 8) | ident_lo
        stx = bytes_list[C.STX_OFFSET]

        # 表11(上行): [7E7E][中心站址][遥测站址]; 表12(下行): [7E7E][遥测站址][中心站址]
        if direction == 0:
            center = bytes_list[2]
            station_raw = bytes_list[3:8]
        else:
            station_raw = bytes_list[2:7]
            center = bytes_list[7]
        pwd = bytes_list[8:10]
        func = bytes_list[10]

        if stx not in (C.STX, C.SYN):
            raise DecodeError(f"报文起始符应为 02H(STX) 或 16H(SYN)，实际 {stx:02X}H")

        serial = bytes_list[C.BODY_OFFSET:C.BODY_OFFSET + C.SERIAL_LEN]
        tx_time_bytes = bytes(bytes_list[C.BODY_OFFSET + C.SERIAL_LEN:
                                         C.BODY_OFFSET + C.SERIAL_LEN + C.TX_TIME_LEN])
        etx_pos = C.BODY_OFFSET + body_len

        if etx_pos + 2 >= total:
            raise DecodeError(f"正文长度 {body_len} 与总长 {total} 不匹配")

        crc_data = bytes(bytes_list[:etx_pos + 1])
        calc_crc = crc16(crc_data)
        recv_crc = (bytes_list[etx_pos + 1] << 8) | bytes_list[etx_pos + 2]

        func_name = C.FUNC_MAP.get(func, f"未知(0x{func:02X})")
        is_uniform = func == 0x31
        encoding = "ASCII" if is_ascii else ("HEX" if is_uniform else "BCD")
        direction_label = "上行（遥测站→中心站）" if direction == 0 else "下行（中心站→遥测站）"

        stn_code = b""
        stn_type = 0
        stn_type_hex = ""
        stn_type_name = ""
        obs_time_bytes = b""

        if direction == 0 and not is_ascii:
            # 上行 HEX/BCD: 表11 结构 — 偏移22/30有 F1F1/F0F0 标识
            can_parse_stn = (
                bytes_list[C.F1_OFFSET] == 0xF1 and bytes_list[C.F1_OFFSET + 1] == 0xF1 and
                bytes_list[C.F0_OFFSET] == 0xF0 and bytes_list[C.F0_OFFSET + 1] == 0xF0
            )
            if can_parse_stn:
                stn_code = bytes(bytes_list[C.STN_CODE_OFFSET:C.STN_CODE_OFFSET + 5])
                stn_type = bytes_list[C.STN_TYPE_OFFSET]
                stn_type_hex = f"{stn_type:02X}"
                stn_type_name = C.STATION_TYPE.get(stn_type, "未知")
                obs_time_bytes = bytes(bytes_list[C.OBS_TIME_OFFSET:
                                                   C.OBS_TIME_OFFSET + C.OBS_TIME_LEN])
                data_start = C.UPLINK_DATA_OFFSET
            else:
                stn_code = bytes(station_raw)
                data_start = C.BODY_OFFSET + C.SERIAL_LEN + C.TX_TIME_LEN
        elif is_ascii:
            # ASCII 编码: 正文为 ASCⅡ 文本，起始于流水号+发报时间之后
            stn_code = bytes(station_raw)
            data_start = C.BODY_OFFSET + C.SERIAL_LEN + C.TX_TIME_LEN
        else:
            stn_code = bytes(station_raw)
            obs_time_bytes = b"\x00" * C.OBS_TIME_LEN
            data_start = C.DOWNLINK_DATA_OFFSET

        station_addr = bytes_to_hex_compact(stn_code) if stn_code else ""
        obs_hex = bytes_to_hex_compact(obs_time_bytes) if obs_time_bytes else ""
        tx_hex = bytes_to_hex_compact(tx_time_bytes)
        pwd_hex = bytes_to_hex_compact(bytes(pwd))
        serial_hex = bytes_to_hex_compact(bytes(serial))

        obs_display = _fmt_bcd_time_nosec(obs_hex) if obs_hex else ""
        tx_display = _fmt_bcd_time_sec(tx_hex)

        data_bytes = bytes(bytes_list[data_start:etx_pos])
        if is_ascii:
            elements = self._parse_ascii_elements(data_bytes)
        else:
            elements = self._parse_elements(data_bytes)

        byte_map = _build_byte_map(bytes_list, direction, etx_pos)
        byte_table = _build_byte_table(bytes_list, direction, etx_pos)

        return DecodedMessage(
            hex_input=bytes_to_hex_compact(frame),
            center_addr=f"{center:02X}",
            station_addr=station_addr,
            password=pwd_hex,
            function_code=func,
            function_name=func_name,
            message_type=func_name,
            direction=direction,
            direction_label=direction_label,
            body_length=body_len,
            serial=serial_hex,
            tx_time=tx_hex,
            tx_time_display=tx_display,
            station_type=stn_type_hex,
            station_type_name=stn_type_name,
            obs_time=obs_hex,
            obs_time_display=obs_display,
            is_uniform=is_uniform,
            encoding=encoding,
            crc_received=recv_crc,
            crc_calculated=calc_crc,
            crc_ok=calc_crc == recv_crc,
            elements=elements,
            byte_map=byte_map,
            byte_table=byte_table,
            raw_frame=frame,
            frame_length=total,
        )

    def _parse_elements(self, data: bytes) -> list[ElementValue]:
        if not data:
            return []
        hex_str = bytes_to_hex_compact(data).lower()
        elements: list[ElementValue] = []
        pos = 0

        while pos + 4 <= len(hex_str):
            code = hex_str[pos:pos + 2]
            pos += 2
            def_hex = hex_str[pos:pos + 2]
            pos += 2
            def_byte = int(def_hex, 16)
            d_len, d_dec = C.parse_def_byte(def_byte)

            if code == "80":
                elements.append(self._parse_80(def_byte, hex_str, pos, d_len))
                pos += d_len * 2
                continue

            if code == "f0" and def_hex == "f0":
                pos += min(10, len(hex_str) - pos)
                continue
            if code == "f1" and def_hex == "f1":
                pos += min(10, len(hex_str) - pos)
                continue

            is_cust = False
            f_len, f_dec = d_len, d_dec

            if code == "ff":
                if pos + 2 > len(hex_str):
                    break
                sub = def_hex
                next_def = hex_str[pos:pos + 2]
                pos += 2
                ndb = int(next_def, 16)
                f_len = (ndb >> 3) & 0x1F
                f_dec = ndb & 0x07
                code = "ff" + sub
                is_cust = True

            need_chars = f_len * 2
            if pos + need_chars > len(hex_str):
                break
            raw_hex = hex_str[pos:pos + need_chars]
            pos += need_chars
            if not raw_hex:
                break

            is_neg = raw_hex[:2] == "ff" and f_len > 1
            entry = C.SL651_CUSTOM.get(code[2:]) if is_cust else C.SL651_ELEMENTS.get(code)
            desc = entry[0] if entry else f"未知({code.upper()})"
            unit = entry[1] if entry else ""
            dt = entry[2] if entry else None

            if dt == "STATUS":
                elements.extend(self._parse_status(raw_hex, f_len))
            elif dt == "F4_ARRAY":
                elements.extend(self._parse_f4_array(raw_hex, f_len))
            elif dt == "F5_ARRAY":
                elements.extend(self._parse_f5_array(raw_hex, f_len, code))
            elif dt == "Hex":
                pv = _safe_hex_val(raw_hex, f_dec, is_neg)
                elements.append(ElementValue(
                    code=code.upper(), name=desc, value=pv[0], unit=unit,
                    raw=pv[1], data_type="Hex", byte_len=f_len, decimal=f_dec, is_sub=is_cust,
                ))
            else:
                pv = _safe_bcd_val(raw_hex, f_dec, is_neg)
                elements.append(ElementValue(
                    code=code.upper(), name=desc, value=pv[0], unit=unit,
                    raw=pv[1], data_type="BCD", byte_len=f_len, decimal=f_dec, is_sub=is_cust,
                ))

        return elements

    def _parse_ascii_elements(self, data: bytes) -> list[ElementValue]:
        """解析 ASCⅡ 编码正文（空格分隔的 ASCII 标识符和值）。"""
        if not data:
            return []
        elements: list[ElementValue] = []
        ascii_text = data.decode("ascii", errors="replace").strip()
        tokens = ascii_text.split()
        i = 0
        # Skip F1F1 section: F1F1 + stn_code + stn_type
        if i < len(tokens) and tokens[i].upper() == "F1F1":
            i += 3  # F1F1, stn_code_hex, stn_type_hex
        # Skip F0F0 section: F0F0 + obs_time
        if i < len(tokens) and tokens[i].upper() == "F0F0":
            i += 2  # F0F0, obs_time_hex

        while i + 1 < len(tokens):
            code = tokens[i]
            value_str = tokens[i + 1]
            entry = C.SL651_ASCII_ELEMENTS.get(code.upper())

            if code.upper() in ("F1F1", "F0F0"):
                i += 1
                continue
            
            desc = entry[0] if entry else f"未知({code})"
            unit = entry[1] if entry else ""

            try:
                if "." in value_str or value_str.startswith("-"):
                    val = float(value_str)
                    decimals = len(value_str.split(".")[1]) if "." in value_str else 0
                else:
                    val = int(value_str)
                    decimals = 0
            except ValueError:
                val = value_str
                decimals = 0

            elements.append(ElementValue(
                code=code.upper(), name=desc, value=val, unit=unit,
                raw=value_str, data_type="ASCII", decimal=decimals,
            ))
            i += 2
        return elements

    @staticmethod
    def _parse_80(def_byte: int, hex_str: str, pos: int, d_len: int) -> ElementValue:
        d_dec = def_byte & 0x07
        need = d_len * 2
        if pos + need > len(hex_str):
            return ElementValue(code="80", name="4G信号强度", value="-", unit="dBm",
                                raw=hex_str[pos:pos + need].upper(), data_type="BCD")
        raw_hex = hex_str[pos:pos + need]
        pv = _safe_bcd_val(raw_hex, d_dec, False)
        return ElementValue(
            code="80", name="4G信号强度", value=pv[0], unit="dBm", raw=pv[1],
            data_type="BCD", byte_len=d_len, decimal=d_dec,
        )

    @staticmethod
    def _parse_status(raw_hex: str, f_len: int) -> list[ElementValue]:
        try:
            sv = int(raw_hex, 16)
        except ValueError:
            return [ElementValue(code="45", name="状态报警", value="-", unit="",
                                 raw=raw_hex.upper(), data_type="STATUS", byte_len=f_len)]
        elements = []
        for i in range(12):
            bit = (sv >> i) & 1
            desc = C.STATUS_BITS[i] if i < len(C.STATUS_BITS) else f"BIT{i}"
            val = C.STATUS_1[i] if bit else C.STATUS_0[i]
            elements.append(ElementValue(
                code=f"BIT{i}", name=desc, value=val, unit="",
                raw=raw_hex.upper(), data_type="STATUS", byte_len=f_len,
            ))
        return elements

    @staticmethod
    def _parse_f4_array(raw_hex: str, f_len: int) -> list[ElementValue]:
        elements = []
        for i in range(min(f_len, 12)):
            if i * 2 + 2 > len(raw_hex):
                break
            bh = raw_hex[i * 2:i * 2 + 2]
            try:
                bv = int(bh, 16)
            except ValueError:
                val = "-"
            else:
                val = "-" if bv == 0xFF else f"{bv / 10:.1f}"
            elements.append(ElementValue(
                code="F4", name=f"第{i + 1}时段({i * 5}min)雨量",
                value=val, unit="mm", raw=bh.upper(),
                data_type="F4_ARRAY", byte_len=1, decimal=1,
            ))
        return elements

    @staticmethod
    def _parse_f5_array(raw_hex: str, f_len: int, code: str) -> list[ElementValue]:
        elements = []
        for i in range(0, min(f_len, 24), 2):
            if i * 2 + 4 > len(raw_hex):
                break
            pair = raw_hex[i * 2:i * 2 + 4]
            try:
                pv = int(pair, 16)
            except ValueError:
                val = "-"
            else:
                val = "-" if pv == 0xFFFF else f"{pv / 100:.2f}"
            elements.append(ElementValue(
                code=code.upper(), name=f"第{i // 2 + 1}时段({i // 2 * 5}min)水位",
                value=val, unit="m", raw=pair.upper(),
                data_type="F5_ARRAY", byte_len=2, decimal=2,
            ))
        return elements


def decode_hex(hex_str: str) -> DecodedMessage:
    return SL651Decoder().decode_hex(hex_str)


def decode(frame: bytes) -> DecodedMessage:
    return SL651Decoder().decode(frame)
