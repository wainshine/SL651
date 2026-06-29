"""SL427-2021 水资源监测数据传输规约 编码器。

帧结构（表3）: 68 L 68 | C | A(5B) | AFN | D [| PW(2B)] [| Tp(7B)] | CS(CRC8) | 16
"""

from __future__ import annotations

from datetime import datetime

from sl651.bcd import bcd_bytes_to_int, datetime_to_bcd, int_to_bcd, int_to_bcd_bytes, safe_bcd_to_int
from sl651.crc import crc8
from . import constants as C


class EncodeError(Exception):
    """编码异常。"""


def _bcd_byte(val: int) -> int:
    return ((val // 10) << 4) | (val % 10)


def encode_address(method: int = 1, admin_code: int = 0, stn_id: int = 1, hex_code: str = "") -> bytes:
    """编码地址域 A（5字节）。

    Args:
        method: 1=方式1(行政区划+站址), 2=方式2(特征码+编码)
        admin_code: 6位行政区划码(方式1)
        stn_id: 站址编号(方式1, 1~60000)
        hex_code: 8位HEX编码字符串(方式2)
    """
    if method == 2:
        if len(hex_code) != 8:
            raise EncodeError(f"方式2 hex_code 必须为8位，当前: {hex_code!r}")
        result = bytearray([0x00])
        for i in range(0, 8, 2):
            result.append(int(hex_code[i:i + 2], 16))
        return bytes(result)
    # 方式1
    admin_bcd = int_to_bcd_bytes(admin_code, 3)
    stn_bin = stn_id.to_bytes(2, "little")
    return admin_bcd + stn_bin


def encode_tp(dt: datetime | None = None, delay: int = 0) -> bytes:
    """编码时间标签 Tp（7字节）。

    前6B: 秒分时日月年 BCD
    第7B: 允许传输延时时长 BIN (min)
    """
    if dt is None:
        dt = datetime.now()
    return bytes([
        _bcd_byte(dt.second),
        _bcd_byte(dt.minute),
        _bcd_byte(dt.hour),
        _bcd_byte(dt.day),
        _bcd_byte(dt.month),
        _bcd_byte(dt.year - 2000),
        delay & 0xFF,
    ])


def _encode_bcd_le(value: int, byte_len: int) -> bytes:
    """整数 -> BCD 小端编码。"""
    return bytes(reversed(int_to_bcd_bytes(value, byte_len)))


class SL427Encoder:
    """SL427 报文编码器。"""

    def __init__(self, addr_bytes: bytes | None = None):
        self.addr_bytes = addr_bytes or encode_address()

    def build_frame(
        self,
        afn: int,
        ctrl_word: int,
        data: bytes = b"",
        tp: bytes | None = None,
        pw: bytes | None = None,
    ) -> bytes:
        """构造完整 SL427 帧。

        Args:
            afn: 功能码
            ctrl_word: 控制域 C（用 make_ctrl 构造）
            data: 数据域 D
            tp: 时间标签 Tp (7B, None=不含)
            pw: 密码 PW (2B, None=不含)
        """
        user = bytearray()
        user.append(ctrl_word & 0xFF)
        user.extend(self.addr_bytes)
        user.append(afn & 0xFF)
        user.extend(data)
        if pw is not None:
            user.extend(pw)
        if tp is not None:
            user.extend(tp)

        L = len(user)
        cs = crc8(bytes(user))

        frame = bytearray([C.START_BYTE, L, C.START_BYTE])
        frame.extend(user)
        frame.append(cs)
        frame.append(C.END_BYTE)
        return bytes(frame)

    def build_heartbeat(self, hb_type: int = 0xF2) -> bytes:
        """链路检测帧 (AFN=02H, 无AUX)。"""
        ctrl = C.make_ctrl(dir_=1, func_code=0x00)
        return self.build_frame(0x02, ctrl, bytes([hb_type & 0xFF]))

    def build_self_report_c0(
        self,
        func_code: int,
        data: bytes,
        tp: datetime | None = None,
        alarm: int = 0,
        state: int = 0,
    ) -> bytes:
        """自报实时数据帧 (AFN=C0H, AUX=仅Tp)。

        data + alarm(2B BIN) + state(2B BIN) + Tp(7B)
        """
        payload = bytearray(data)
        payload.extend(alarm.to_bytes(2, "little"))
        payload.extend(state.to_bytes(2, "little"))
        tp_bytes = encode_tp(tp, delay=0)
        ctrl = C.make_ctrl(dir_=1, func_code=func_code)
        return self.build_frame(0xC0, ctrl, bytes(payload), tp=tp_bytes)

    def build_query_response(
        self,
        func_code: int,
        data: bytes,
    ) -> bytes:
        """查询响应帧 (AFN=B0H, 无AUX)。"""
        ctrl = C.make_ctrl(dir_=1, func_code=func_code)
        return self.build_frame(0xB0, ctrl, data)
