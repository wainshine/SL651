"""SL651-2014 报文解码器（部分参考 njnrs 解析思路）。"""

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
    warnings: list[str] = field(default_factory=list)  # 非致命解析告警（如定义符与规范不符）

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
            "warnings": list(self.warnings),
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


def _ascii_time_step_desc(code: str) -> str | None:
    """识别 ASCII 时间步长码 DRxnn（x=D/H/N，nn=取值范围，规约表C.2）。

    返回描述（含单位），非时间步长码返回 None。表 C.1 中标识符写作 DRxnn，
    实际报文中 x 为 D/H/N 之一。
    """
    c = code.upper()
    if c == "DRXNN":
        return "时间步长码"
    if len(c) == 5 and c.startswith("DR") and c[2] in ("D", "H", "N") and c[3:].isdigit():
        unit = {"D": "日", "H": "小时", "N": "分钟"}[c[2]]
        return f"时间步长码({unit})"
    return None


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
    if decimals == 0:
        return (int(r), hex_str.upper())
    return (r, hex_str.upper())


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
    if decimals == 0:
        return (int(r), hex_str.upper())
    return (r, hex_str.upper())


def _build_byte_map(bytes_list: list[int], direction: int, etx_pos: int, syn_pad: int = 0) -> str:
    f1_pos = 22 + syn_pad  # F1F1 站码标识（上行）
    f0_pos = 30 + syn_pad  # F0F0 观测时间标识（上行）
    lines = []
    for offset in range(0, len(bytes_list), 16):
        chunk = bytes_list[offset: offset + 16]
        parts = []
        for i, b in enumerate(chunk):
            h = f"{b:02X}"
            idx = offset + i
            if idx < 2:
                h = f"*{h}*"
            elif idx == 2:
                h = f"[{h}]"
            elif idx == 13 or idx == etx_pos:
                h = f"<{h}>"
            elif direction == 0 and idx in (f1_pos, f1_pos + 1, f0_pos, f0_pos + 1):
                h = f"<{h}>"
            elif idx > etx_pos:
                h = f"*{h}*"
            parts.append(h)
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _build_byte_table(bytes_list: list[int], direction: int, etx_pos: int, syn_pad: int = 0) -> list[dict]:
    p = syn_pad  # SYN 多包帧正文字段整体后移 3 字节
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
            (13, 13, "STX(02)/SYN(16)"),
        ]
        if syn_pad:
            fields.append((14, 16, "SYN 多包(包总数/序列/包长)"))
        fields += [
            (14 + p, 15 + p, "流水号"),
            (16 + p, 21 + p, "发报时间(BCD 6B)"),
            (22 + p, 23 + p, "站码标识 F1F1"),
            (24 + p, 28 + p, "站码(5字节)"),
            (29 + p, 29 + p, "测站类别"),
            (30 + p, 31 + p, "观测时间标识 F0F0"),
            (32 + p, 36 + p, "观测时间(BCD 5B)"),
            (37 + p, etx_pos - 1, "水文要素数据"),
        ]
    else:
        fields += [
            (2, 6, "遥测站地址(5字节)"),
            (7, 7, "中心站址"),
            (8, 9, "密码"),
            (10, 10, "功能码"),
            (11, 12, "报文标识"),
            (13, 13, "STX(02)/SYN(16)"),
        ]
        if syn_pad:
            fields.append((14, 16, "SYN 多包(包总数/序列/包长)"))
        fields += [
            (14 + p, 15 + p, "流水号"),
            (16 + p, 21 + p, "发报时间(BCD 6B)"),
            (22 + p, etx_pos - 1, "响应数据"),
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
        if cleaned[:4].upper() not in ("7E7E", "0101") and cleaned[:2].upper() != "01":
            raise DecodeError("报文不是以 7E7E(HEX/BCD)、0101(旧ASCII) 或 01(ASCII) 开头")
        return self.decode(bytes.fromhex(cleaned))

    def decode(self, frame: bytes) -> DecodedMessage:
        if len(frame) < C.BODY_OFFSET + 4:
            raise DecodeError(f"报文太短: {len(frame)} 字节")
        if frame[0] == C.START_BYTE:
            if len(frame) < 2 or frame[1] != C.START_BYTE:
                raise DecodeError("报文起始符应为 7E7E")
        elif frame[0] != C.SOH:
            raise DecodeError(f"报文不是以 7E7E(HEX/BCD) 或 01(ASCII) 开头: {frame[0]:02X}H")

        bytes_list = list(frame)
        total = len(bytes_list)
        is_ascii = frame[0] == C.SOH
        is_new_ascii = is_ascii and len(frame) > 1 and frame[1] != C.SOH

        if is_new_ascii:
            return self._decode_new_ascii(frame, bytes_list, total)

        return self._decode_binary(frame, bytes_list, total)

    def _decode_new_ascii(self, frame: bytes, bytes_list: list[int], total: int) -> DecodedMessage:
        if total < C.ASCII_DATA_OFFSET + 3:
            raise DecodeError(f"ASCII 报文太短: {total} 字节")

        try:
            center = int(frame[1:3].decode("ascii"), 16)
            station_addr = frame[3:13].decode("ascii")
            station_raw = bytes.fromhex(station_addr)
            password = int(frame[13:17].decode("ascii"), 16)
            func = int(frame[17:19].decode("ascii"), 16)
            ident_raw = int(frame[19:23].decode("ascii"), 16)
            serial_raw = int(frame[24:28].decode("ascii"), 16)
            tx_time_bytes = bytes.fromhex(frame[28:40].decode("ascii"))
        except (ValueError, UnicodeDecodeError) as e:
            raise DecodeError(f"ASCII 报文头部解析失败: {e}") from e
        ident_hi = (ident_raw >> 8) & 0xFF
        ident_lo = ident_raw & 0xFF
        direction = (ident_hi >> 7) & 1
        body_len = ((ident_hi & 0x0F) << 8) | ident_lo

        stx = frame[C.ASCII_STX_OFFSET]
        if stx != C.STX:
            raise DecodeError(f"ASCII 报文 STX 应为 02H，实际 {stx:02X}H")

        serial_hex_str = f"{serial_raw:04X}"
        tx_hex_str = bytes_to_hex_compact(tx_time_bytes)

        etx_pos = C.ASCII_BODY_OFFSET + body_len
        if etx_pos + C.ASCII_CRC_LEN >= total:
            raise DecodeError(f"ASCII 正文长度 {body_len} 与总长 {total} 不匹配")

        if frame[etx_pos] != C.ETX:
            raise DecodeError(f"ASCII 报文 ETX 应为 03H，实际 {frame[etx_pos]:02X}H")

        crc_data = bytes(frame[:etx_pos + 1])
        calc_crc = crc16(crc_data)
        try:
            recv_crc = int(frame[etx_pos + 1:etx_pos + 1 + C.ASCII_CRC_LEN].decode("ascii"), 16)
        except (ValueError, UnicodeDecodeError) as e:
            raise DecodeError(f"ASCII 报文 CRC 字段解析失败: {e}") from e

        data_bytes = bytes(bytes_list[C.ASCII_DATA_OFFSET:etx_pos])

        func_name = C.FUNC_MAP.get(func, f"未知(0x{func:02X})")
        is_uniform = func == 0x31
        encoding = "ASCII"
        direction_label = "上行（遥测站→中心站）" if direction == 0 else "下行（中心站→遥测站）"

        pwd_hex = f"{password:04X}"
        tx_display = _fmt_bcd_time_sec(tx_hex_str)

        stn_type_hex = ""
        stn_type_name = ""
        obs_hex = ""
        obs_display = ""

        elements = self._parse_ascii_elements(data_bytes)
        obs_hex, obs_display, stn_type_hex, stn_type_name = \
            self._extract_ascii_times(data_bytes)

        byte_map = ""
        byte_table = []

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
            serial=serial_hex_str,
            tx_time=tx_hex_str,
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

    def _decode_binary(self, frame: bytes, bytes_list: list[int], total: int) -> DecodedMessage:
        is_ascii = frame[0] == C.SOH
        ident_hi = bytes_list[11]
        ident_lo = bytes_list[12]
        direction = (ident_hi >> 7) & 1
        body_len = ((ident_hi & 0x0F) << 8) | ident_lo
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

        syn_pad = 3 if stx == C.SYN else 0  # SYN 多包帧: 包总数(1B)+序列号(1B)+包长度(1B)
        body_start = C.BODY_OFFSET + syn_pad
        serial = bytes_list[body_start: body_start + C.SERIAL_LEN]
        tx_time_bytes = bytes(bytes_list[body_start + C.SERIAL_LEN:
                                         body_start + C.SERIAL_LEN + C.TX_TIME_LEN])
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
            f1_pos = C.F1_OFFSET + syn_pad
            f0_pos = C.F0_OFFSET + syn_pad
            can_parse_stn = (
                f0_pos + 1 < etx_pos and
                bytes_list[f1_pos] == 0xF1 and bytes_list[f1_pos + 1] == 0xF1 and
                bytes_list[f0_pos] == 0xF0 and bytes_list[f0_pos + 1] == 0xF0
            )
            if can_parse_stn:
                stn_code = bytes(bytes_list[C.STN_CODE_OFFSET + syn_pad:C.STN_CODE_OFFSET + 5 + syn_pad])
                stn_type = bytes_list[C.STN_TYPE_OFFSET + syn_pad]
                stn_type_hex = f"{stn_type:02X}"
                stn_type_name = C.STATION_TYPE.get(stn_type, "未知")
                obs_time_bytes = bytes(bytes_list[C.OBS_TIME_OFFSET + syn_pad:
                                                    C.OBS_TIME_OFFSET + C.OBS_TIME_LEN + syn_pad])
                data_start = C.UPLINK_DATA_OFFSET + syn_pad
            else:
                stn_code = bytes(station_raw)
                data_start = body_start + C.SERIAL_LEN + C.TX_TIME_LEN
        elif is_ascii:
            stn_code = bytes(station_raw)
            data_start = body_start + C.SERIAL_LEN + C.TX_TIME_LEN
        else:
            stn_code = bytes(station_raw)
            obs_time_bytes = b""
            data_start = C.DOWNLINK_DATA_OFFSET + syn_pad

        station_addr = bytes_to_hex_compact(stn_code) if stn_code else ""
        obs_hex = bytes_to_hex_compact(obs_time_bytes) if obs_time_bytes else ""
        tx_hex = bytes_to_hex_compact(tx_time_bytes)
        pwd_hex = bytes_to_hex_compact(bytes(pwd))
        serial_hex = bytes_to_hex_compact(bytes(serial))

        obs_display = _fmt_bcd_time_nosec(obs_hex) if obs_hex else ""
        tx_display = _fmt_bcd_time_sec(tx_hex)

        warnings: list[str] = []
        data_bytes = bytes(bytes_list[data_start:etx_pos])
        if is_ascii:
            elements = self._parse_ascii_elements(data_bytes)
        else:
            elements, warnings = self._parse_elements(data_bytes, func)

        byte_map = _build_byte_map(bytes_list, direction, etx_pos, syn_pad)
        byte_table = _build_byte_table(bytes_list, direction, etx_pos, syn_pad)

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
            warnings=warnings,
        )

    def _parse_elements(
        self, data: bytes, function_code: int = 0
    ) -> tuple[list[ElementValue], list[str]]:
        warnings: list[str] = []
        if not data:
            return [], warnings
        hex_str = bytes_to_hex_compact(data).lower()
        elements: list[ElementValue] = []
        pos = 0
        is_uniform = function_code == 0x31

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
                pos += 10  # F0F0信息组=标识(2B)+观测时间(5B), 已读2B标识, 跳5B
                continue
            if code == "f1" and def_hex == "f1":
                pos += 12
                continue
            if code in ("f0", "f1"):
                # F0/F1 引导符但定义符不匹配，报文已失同步，终止要素解析
                break

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

            entry = C.SL651_CUSTOM.get(code[2:]) if is_cust else C.SL651_ELEMENTS.get(code)
            desc = entry[0] if entry else f"未知({code.upper()})"
            unit = entry[1] if entry else ""
            dt = entry[2] if entry else None

            # F4/F5~FC 数组长度按规范固定（附录C 表C.1），不信任定义符长度
            if dt in ("F4_ARRAY", "F5_ARRAY"):
                fixed_len = 12 if dt == "F4_ARRAY" else 24
                if f_len != fixed_len:
                    warnings.append(
                        f"要素 {code.upper()} 定义符声明 {f_len} 字节，"
                        f"按规范固定 {fixed_len} 字节解析"
                    )
                available = len(hex_str) - pos
                if available < fixed_len * 2:
                    warnings.append(
                        f"要素 {code.upper()} 数据不足规范 {fixed_len} 字节"
                        f"（仅 {available // 2} 字节），按现有数据解析"
                    )
                need_chars = min(fixed_len * 2, available)
                raw_hex = hex_str[pos:pos + need_chars]
                pos += need_chars
                if not raw_hex:
                    break
                elements.extend(self._make_element(
                    code, desc, unit, dt, raw_hex, fixed_len, f_dec, False, is_cust
                ))
                if is_uniform and fixed_len > 0:
                    self._consume_uniform_groups(
                        hex_str, pos, fixed_len, dt, code, desc, unit, f_dec, elements
                    )
                    pos = len(hex_str)
                continue

            need_chars = f_len * 2
            if pos + need_chars > len(hex_str):
                break
            raw_hex = hex_str[pos:pos + need_chars]
            pos += need_chars
            if not raw_hex:
                break

            # 0xFF 负数前缀仅适用 BCD 编码（规约 6.6.3.3），Hex 型数据的 0xFF 是合法字节
            is_neg = raw_hex[:2] == "ff" and f_len > 1 and dt != "Hex"
            elements.extend(self._make_element(
                code, desc, unit, dt, raw_hex, f_len, f_dec, is_neg, is_cust
            ))

            # 均匀报：标识符组只出现一次，其后为重复数据组（§6.6.4.4 表30 注d）
            if is_uniform and f_len > 0:
                remaining = len(hex_str) - pos
                if remaining > 0 and remaining % (f_len * 2) == 0:
                    nxt = hex_str[pos:pos + 2]
                    if nxt not in C.SL651_ELEMENTS and nxt not in ("f0", "f1", "ff"):
                        self._consume_uniform_groups(
                            hex_str, pos, f_len, dt, code, desc, unit, f_dec, elements
                        )
                        pos = len(hex_str)

        return elements, warnings

    @staticmethod
    def _consume_uniform_groups(
        hex_str: str, pos: int, f_len: int, dt: str | None,
        code: str, desc: str, unit: str, f_dec: int,
        elements: list[ElementValue],
    ) -> None:
        """消费均匀报重复数据组（每组长度一致，无重复标识符）。"""
        while pos + f_len * 2 <= len(hex_str):
            raw = hex_str[pos:pos + f_len * 2]
            pos += f_len * 2
            if dt == "F4_ARRAY":
                elements.extend(SL651Decoder._parse_f4_array(raw, f_len, f_dec))
            elif dt == "F5_ARRAY":
                elements.extend(SL651Decoder._parse_f5_array(raw, f_len, code, f_dec))
            elif dt == "Hex":
                pv = _safe_hex_val(raw, f_dec, False)
                elements.append(ElementValue(
                    code=code.upper(), name=desc, value=pv[0],
                    unit=unit, raw=pv[1], data_type="Hex", byte_len=f_len, decimal=f_dec,
                ))
            else:
                pv = _safe_bcd_val(raw, f_dec, False)
                elements.append(ElementValue(
                    code=code.upper(), name=desc, value=pv[0],
                    unit=unit, raw=pv[1], data_type="BCD", byte_len=f_len, decimal=f_dec,
                ))

    @staticmethod
    def _make_element(
        code: str, desc: str, unit: str, dt: str | None, raw_hex: str,
        f_len: int, f_dec: int, is_neg: bool, is_cust: bool,
    ) -> list[ElementValue]:
        if dt == "STATUS":
            return SL651Decoder._parse_status(raw_hex, f_len)
        if dt == "F4_ARRAY":
            return SL651Decoder._parse_f4_array(raw_hex, f_len, f_dec)
        if dt == "F5_ARRAY":
            return SL651Decoder._parse_f5_array(raw_hex, f_len, code, f_dec)
        if dt == "Hex":
            if code == "f3":
                # 图片二进制不做数值化，显示字节数 + hex 预览
                preview = raw_hex[:32].upper()
                if len(raw_hex) > 32:
                    preview += "..."
                return [ElementValue(
                    code=code.upper(), name=desc,
                    value=f"<图片数据 {f_len} 字节: {preview}>", unit="",
                    raw=raw_hex.upper(), data_type="Hex", byte_len=f_len,
                    decimal=f_dec, is_sub=is_cust,
                )]
            pv = _safe_hex_val(raw_hex, f_dec, is_neg)
            return [ElementValue(
                code=code.upper(), name=desc, value=pv[0], unit=unit,
                raw=pv[1], data_type="Hex", byte_len=f_len, decimal=f_dec, is_sub=is_cust,
            )]
        pv = _safe_bcd_val(raw_hex, f_dec, is_neg)
        return [ElementValue(
            code=code.upper(), name=desc, value=pv[0], unit=unit,
            raw=pv[1], data_type="BCD", byte_len=f_len, decimal=f_dec, is_sub=is_cust,
        )]

    def _parse_ascii_elements(self, data: bytes) -> list[ElementValue]:
        """解析 ASCⅡ 编码正文（空格分隔的 ASCII 标识符和值）。"""
        if not data:
            return []
        elements: list[ElementValue] = []
        ascii_text = data.decode("ascii", errors="replace").strip()
        tokens = ascii_text.split()
        i = 0
        # Skip ST section: ST/F1F1 + stn_code + stn_type
        if i < len(tokens) and tokens[i].upper() in ("F1F1", "ST"):
            i += 3
        # Skip TT section: TT/F0F0 + obs_time
        if i < len(tokens) and tokens[i].upper() in ("F0F0", "TT"):
            i += 2

        while i + 1 < len(tokens):
            code = tokens[i]
            value_str = tokens[i + 1]
            ts_desc = _ascii_time_step_desc(code)
            if ts_desc is not None:
                entry = (ts_desc, "")
            else:
                entry = C.SL651_ASCII_ELEMENTS.get(code.upper())

            if code.upper() in ("F1F1", "F0F0", "ST", "TT"):
                i += 1
                continue

            # 收集多值数组：检查后续 token 是否为纯数值
            values = [value_str]
            j = i + 2
            while j < len(tokens):
                nxt = tokens[j]
                nxt_entry = C.SL651_ASCII_ELEMENTS.get(nxt.upper())
                if (nxt_entry or _ascii_time_step_desc(nxt) is not None
                        or nxt.upper() in ("F1F1", "F0F0", "ST", "TT")):
                    break
                try:
                    float(nxt)
                except ValueError:
                    break
                values.append(nxt)
                j += 1

            desc = entry[0] if entry else f"未知({code})"
            unit = entry[1] if entry else ""

            for vi, vs in enumerate(values):
                try:
                    if "." in vs or vs.startswith("-"):
                        val = float(vs)
                        decimals = len(vs.split(".")[1]) if "." in vs else 0
                    else:
                        val = int(vs)
                        decimals = 0
                except ValueError:
                    val = vs
                    decimals = 0

                label = desc if vi == 0 else f"{desc}[{vi}]"
                elements.append(ElementValue(
                    code=code.upper(), name=label, value=val, unit=unit,
                    raw=vs, data_type="ASCII", decimal=decimals,
                ))
            i = j
        return elements

    def _extract_ascii_times(
        self, data: bytes
    ) -> tuple[str, str, str, str]:
        ascii_text = data.decode("ascii", errors="replace").strip()
        tokens = ascii_text.split()
        i = 0
        stn_type_hex = ""
        stn_type_name = ""
        obs_hex = ""
        obs_display = ""

        if i < len(tokens) and tokens[i].upper() in ("F1F1", "ST"):
            # tokens[i+1] = station code, tokens[i+2] = station type hex
            if i + 2 < len(tokens):
                stn_type_hex = tokens[i + 2]
                try:
                    stn_type = int(stn_type_hex, 16) if len(stn_type_hex) == 2 else -1
                except ValueError:
                    stn_type = -1
                stn_type_name = C.STATION_TYPE.get(stn_type, "未知")
            i += 3

        if i < len(tokens) and tokens[i].upper() in ("F0F0", "TT"):
            if i + 1 < len(tokens):
                obs_time_str = tokens[i + 1]
                obs_hex = obs_time_str
                obs_display = _fmt_bcd_time_nosec(obs_time_str)

        return obs_hex, obs_display, stn_type_hex, stn_type_name

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
        """解析 45H 状态报警。注：当前缩减为 12 位，规范表58 为 4B/32 位。"""
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
    def _parse_f4_array(raw_hex: str, f_len: int, decimals: int = 1) -> list[ElementValue]:
        """F4H 5分钟时段雨量数组（规范固定 12 字节，分辨率 0.1mm）。

        decimals 仅用于兜底；规范附录C 表C.1 固定 1 位小数。
        """
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
    def _parse_f5_array(
        raw_hex: str, f_len: int, code: str, decimals: int = 2
    ) -> list[ElementValue]:
        """F5H~FCH 5分钟间隔相对水位数组（规范固定 24 字节，分辨率 0.01m）。

        规范附录C 表C.1 固定 12 组 × 2 字节 / 0.01m，故不采用定义符低 3 位小数。
        """
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
