"""SL427-2021 水资源监测数据传输规约 编码器。

帧结构（表3）: 68 L 68 | C | A(5B) | AFN | D [| PW(2B)] [| Tp(7B)] | CS(CRC8) | 16
"""

from __future__ import annotations

from datetime import datetime

from sl651.bcd import int_to_bcd_bytes
from sl651.crc import crc8
from . import constants as C


class EncodeError(Exception):
    """编码异常。"""


def _bcd_byte(val: int) -> int:
    if not 0 <= val <= 99:
        raise EncodeError(f"BCD 字节值超范围(0~99): {val}")
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
        try:
            for i in range(0, 8, 2):
                result.append(int(hex_code[i:i + 2], 16))
        except ValueError:
            raise EncodeError(f"方式2 hex_code 含非 hex 字符: {hex_code!r}") from None
        return bytes(result)
    if method != 1:
        raise EncodeError(f"method 只支持 1/2，当前: {method}")
    if not 0 <= admin_code <= 999999:
        raise EncodeError(f"admin_code 超范围(0~999999): {admin_code}")
    if not 1 <= stn_id <= 60000:
        raise EncodeError(f"stn_id 超范围(1~60000): {stn_id}")
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
    if not 2000 <= dt.year <= 2099:
        raise EncodeError(f"Tp 年份超范围(2000~2099): {dt.year}")
    if not 0 <= delay <= 255:
        raise EncodeError(f"Tp 传输延时时长超范围(0~255): {delay}")
    return bytes([
        _bcd_byte(dt.second),
        _bcd_byte(dt.minute),
        _bcd_byte(dt.hour),
        _bcd_byte(dt.day),
        _bcd_byte(dt.month),
        _bcd_byte(dt.year - 2000),
        delay,
    ])



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
        if not 0 <= afn <= 0xFF:
            raise EncodeError(f"afn 超范围(0~0xFF): {afn}")
        if not 0 <= ctrl_word <= 0xFF:
            raise EncodeError(f"ctrl_word 超范围(0~0xFF): {ctrl_word}")
        if tp is not None and len(tp) != 7:
            raise EncodeError(f"tp 必须为 7 字节，当前 {len(tp)} 字节")
        if pw is not None and len(pw) != 2:
            raise EncodeError(f"pw 必须为 2 字节，当前 {len(pw)} 字节")
        if len(self.addr_bytes) != 5:
            raise EncodeError(f"addr_bytes 必须为 5 字节，当前 {len(self.addr_bytes)} 字节")

        user = bytearray()
        user.append(ctrl_word)
        user.extend(self.addr_bytes)
        user.append(afn)
        user.extend(data)
        if pw is not None:
            user.extend(pw)
        if tp is not None:
            user.extend(tp)

        L = len(user)
        if L > 255:
            raise EncodeError(f"用户区长度超范围(L≤255): {L}")
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
        alarm: int = 0,
        state: int = 0,
    ) -> bytes:
        """查询响应帧 (AFN=B0H, 无AUX)。

        规范7.3.22：数据域最后4B=报警状态(2B)+终端机状态(2B)。
        """
        payload = bytearray(data)
        payload.extend(alarm.to_bytes(2, "little"))
        payload.extend(state.to_bytes(2, "little"))
        ctrl = C.make_ctrl(dir_=1, func_code=func_code)
        return self.build_frame(0xB0, ctrl, bytes(payload))

    def build_self_report_81(
        self,
        func_code: int,
        data: bytes,
        tp: datetime | None = None,
        alarm: int = 0,
        state: int = 0,
    ) -> bytes:
        """自报告警数据帧 (AFN=81H, AUX=仅Tp)。

        规范7.5.2：alarm(2B BIN) + data + state(2B BIN) + Tp(7B)
        """
        payload = bytearray()
        payload.extend(alarm.to_bytes(2, "little"))
        payload.extend(data)
        payload.extend(state.to_bytes(2, "little"))
        tp_bytes = encode_tp(tp, delay=0)
        ctrl = C.make_ctrl(dir_=1, func_code=func_code)
        return self.build_frame(0x81, ctrl, bytes(payload), tp=tp_bytes)

    def build_self_report_82(
        self,
        func_code: int,
        data: bytes,
        tp: datetime | None = None,
        alarm: int = 0,
        state: int = 0,
    ) -> bytes:
        """人工置数帧 (AFN=82H, AUX=仅Tp)。

        data + alarm(2B BIN) + state(2B BIN) + Tp(7B)
        """
        payload = bytearray(data)
        payload.extend(alarm.to_bytes(2, "little"))
        payload.extend(state.to_bytes(2, "little"))
        tp_bytes = encode_tp(tp, delay=0)
        ctrl = C.make_ctrl(dir_=1, func_code=func_code)
        return self.build_frame(0x82, ctrl, bytes(payload), tp=tp_bytes)

    def build_self_report_84(
        self,
        voltage: float,
        tp: datetime | None = None,
    ) -> bytes:
        """自报电压帧 (AFN=84H, AUX=仅Tp)。

        规范7.5.5/表B.98：数据域仅 2B BCD 电压值，不含 alarm/state。
        """
        v = int(round(voltage * 100))
        data = bytes(reversed(int_to_bcd_bytes(v, 2)))
        ctrl = C.make_ctrl(dir_=1, func_code=0x0D)
        return self.build_frame(0x84, ctrl, data)

    def build_param_set_frame(
        self,
        afn: int,
        func_code: int,
        data: bytes,
        pw: int = 0,
        tp: datetime | None = None,
    ) -> bytes:
        """通用参数设置帧 (AFN=10H~4FH, AUX=PW+Tp, 下行)。"""
        ctrl = C.make_ctrl(dir_=0, func_code=func_code)
        pw_bytes = C.encode_pw(0, pw)
        return self.build_frame(afn, ctrl, data, tp=encode_tp(tp), pw=pw_bytes)

    # ------------------------------------------------------------------
    # 参数设置便捷方法 (AFN=10H~34H)
    # ------------------------------------------------------------------

    def build_set_addr(self, new_addr_bytes: bytes, pw: int = 0) -> bytes:
        """设置地址 (AFN=10H)。"""
        return self.build_param_set_frame(0x10, 0x00, new_addr_bytes, pw)

    def build_set_clock(self, dt: datetime | None = None, pw: int = 0) -> bytes:
        """设置时钟 (AFN=11H)。6B BCD: 秒分时日月(星期)年。
        
        第5字节 D5~D7=星期(1=周一~7=周日), D4~D0=月。
        """
        if dt is None:
            dt = datetime.now()
        wd = dt.weekday() + 1  # Python weekday: 0=周一
        week_month = ((wd & 0x07) << 5) | (dt.month & 0x1F)
        data = bytes([_bcd_byte(dt.second), _bcd_byte(dt.minute),
                       _bcd_byte(dt.hour), _bcd_byte(dt.day),
                       week_month,
                       _bcd_byte(dt.year - 2000)])
        return self.build_param_set_frame(0x11, 0x00, data, pw)

    def build_set_work_mode(self, mode: int, pw: int = 0) -> bytes:
        """设置工作模式 (AFN=12H)。mode: 0=兼容, 1=自报, 2=查询/应答, 3=调试（规约 §7.2.4）。"""
        return self.build_param_set_frame(0x12, 0x00, bytes([mode & 0xFF]), pw)

    def build_set_recharge(self, amount: float, pw: int = 0) -> bytes:
        """设置充值量 (AFN=15H)。amount 单位 m³（4B BCD 小端，规约 §7.2.5 表13）。"""
        v = int(round(amount))
        data = bytes(reversed(int_to_bcd_bytes(v, 4)))
        return self.build_param_set_frame(0x15, 0x00, data, pw)

    def build_set_ic_card_on(self, pw: int = 0) -> bytes:
        """IC卡功能有效 (AFN=30H)。"""
        return self.build_param_set_frame(0x30, 0x00, b"", pw)

    def build_set_ic_card_off(self, pw: int = 0) -> bytes:
        """取消IC卡功能 (AFN=31H)。"""
        return self.build_param_set_frame(0x31, 0x00, b"", pw)
