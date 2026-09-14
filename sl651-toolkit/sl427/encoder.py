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


def _bcd_le(value: int, nbytes: int) -> bytes:
    """整数 -> 小端 2 位一组 BCD（SL427 数据域常用，低位字节在前）。"""
    try:
        return bytes(reversed(int_to_bcd_bytes(value, nbytes)))
    except ValueError as e:
        raise EncodeError(f"BCD 值超范围: {value} ({nbytes} 字节): {e}") from e


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

    def build_self_report_84(self, voltage: float) -> bytes:
        """自报电压帧 (AFN=84H)。

        规范7.5.5/表B.98：自报帧数据域仅 2B BCD 电压值（低位在前），
        不含 alarm/state，也不含 Tp（Tp 仅出现在 B.99 确认帧）。
        """
        v = int(round(voltage * 100))
        try:
            data = bytes(reversed(int_to_bcd_bytes(v, 2)))
        except ValueError as e:
            raise EncodeError(f"电压值超范围(0~999.99V): {voltage}") from e
        ctrl = C.make_ctrl(dir_=1, func_code=0x0D)
        return self.build_frame(0x84, ctrl, data)

    def build_param_set_frame(
        self,
        afn: int,
        func_code: int,
        data: bytes,
        pw: int = 0,
        tp: datetime | None = None,
        key1: int = 0,
    ) -> bytes:
        """通用参数设置帧 (AFN=10H~4FH, AUX=PW+Tp, 下行)。

        key1/pw 组成密码 PW（表9）：key1 1位 BCD，pw 3位 BCD。
        """
        if not 0 <= key1 <= 9:
            raise EncodeError(f"PW key1 超范围(0~9): {key1}")
        if not 0 <= pw <= 999:
            raise EncodeError(f"PW key2 超范围(0~999): {pw}")
        ctrl = C.make_ctrl(dir_=0, func_code=func_code)
        pw_bytes = C.encode_pw(key1, pw)
        return self.build_frame(afn, ctrl, data, tp=encode_tp(tp), pw=pw_bytes)

    # ------------------------------------------------------------------
    # 参数设置便捷方法 (AFN=10H~34H)
    # ------------------------------------------------------------------

    def build_set_addr(self, new_addr_bytes: bytes, pw: int = 0) -> bytes:
        """设置地址 (AFN=10H)，数据域固定 5B（规约表B.3）。"""
        if len(new_addr_bytes) != 5:
            raise EncodeError(
                f"设置地址数据域必须为 5 字节，当前 {len(new_addr_bytes)} 字节")
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
        try:
            data = bytes(reversed(int_to_bcd_bytes(v, 4)))
        except ValueError as e:
            raise EncodeError(f"充值量超范围(0~99999999 m³): {amount}") from e
        return self.build_param_set_frame(0x15, 0x00, data, pw)

    def build_set_ic_card_on(self, pw: int = 0) -> bytes:
        """IC卡功能有效 (AFN=30H)。"""
        return self.build_param_set_frame(0x30, 0x00, b"", pw)

    def build_set_ic_card_off(self, pw: int = 0) -> bytes:
        """取消IC卡功能 (AFN=31H)。"""
        return self.build_param_set_frame(0x31, 0x00, b"", pw)

    # ------------------------------------------------------------------
    # 参数设置便捷方法 (AFN=16H~20H，规约 7.2.6~7.2.16)
    # ------------------------------------------------------------------

    def build_set_recharge_alarm(self, amount_m3: float, pw: int = 0) -> bytes:
        """设置剩余水量报警值 (AFN=16H)。3B 压缩 BCD，0~999999 m³（表14）。"""
        v = int(round(amount_m3))
        if not 0 <= v <= 999999:
            raise EncodeError(f"剩余水量报警值超范围(0~999999 m³): {amount_m3}")
        return self.build_param_set_frame(0x16, 0x00, _bcd_le(v, 3), pw)

    def build_set_level_limits(
        self, points: list[tuple[float, float, float]], pw: int = 0
    ) -> bytes:
        """设置水位基值/上下限 (AFN=17H)，每点 7B（表15/16）。

        points: [(base, lower_offset, upper_offset), ...]
          base: -7999.99~7999.99 m（第3字节 D7 为符号位）
          lower/upper_offset: 0~99.99 m（相对基值的偏移）
        """
        data = bytearray()
        for base, lower, upper in points:
            base_v = int(round(abs(base) * 100))
            if base_v > 799999:
                raise EncodeError(f"水位基值超范围(-7999.99~7999.99): {base}")
            b = bytearray(_bcd_le(base_v, 3))
            if base < 0:
                b[2] |= 0x80
            data.extend(b)
            for off in (lower, upper):
                ov = int(round(off * 100))
                if not 0 <= ov <= 9999:
                    raise EncodeError(f"水位上下限偏移超范围(0~99.99): {off}")
                data.extend(_bcd_le(ov, 2))
        return self.build_param_set_frame(0x17, 0x00, bytes(data), pw)

    def build_set_pressure_limits(
        self, points: list[tuple[float, float]], pw: int = 0
    ) -> bytes:
        """设置水压上/下限 (AFN=18H)，每点 8B（上限4B + 下限4B，小端 BCD，表17）。

        points: [(upper_kpa, lower_kpa), ...]，范围 0~999999.99 kPa
        """
        data = bytearray()
        for upper, lower in points:
            for val in (upper, lower):
                v = int(round(val * 100))
                if not 0 <= v <= 99999999:
                    raise EncodeError(f"水压值超范围(0~999999.99 kPa): {val}")
                data.extend(_bcd_le(v, 4))
        return self.build_param_set_frame(0x18, 0x00, bytes(data), pw)

    def build_set_water_quality(
        self, afn: int, params: list[tuple[int, int]], pw: int = 0
    ) -> bytes:
        """设置水质参数种类及上/下限值 (AFN=19H/1AH)，5B 位图 + N×4B（表18）。

        params: [(bit_index, scaled_value), ...]
          bit_index: 0~39（表18 对应位）
          scaled_value: 已按该参数小数位缩放后的整数（0~99999999）
        """
        if afn not in (0x19, 0x1A):
            raise EncodeError(f"AFN 仅支持 19H/1AH: {afn:#x}")
        mask = 0
        for bit, _ in params:
            if not 0 <= bit <= 39:
                raise EncodeError(f"水质参数位号超范围(0~39): {bit}")
            mask |= 1 << bit
        data = bytearray(mask.to_bytes(5, "little"))
        for _, val in params:
            v = int(round(val))
            if not 0 <= v <= 99999999:
                raise EncodeError(f"水质参数值超范围(0~99999999): {val}")
            data.extend(_bcd_le(v, 4))
        return self.build_param_set_frame(afn, 0x00, bytes(data), pw)

    def build_set_water_amount(
        self, values: list[float], pw: int = 0
    ) -> bytes:
        """设置水量初始值 (AFN=1BH)，每个水表 5B BCD（表19），0~7999999999 m³。"""
        data = bytearray()
        for val in values:
            v = int(round(val))
            if not 0 <= v <= 7999999999:
                raise EncodeError(f"水量初始值超范围(0~7999999999): {val}")
            data.extend(_bcd_le(v, 5))
        return self.build_param_set_frame(0x1B, 0x00, bytes(data), pw)

    def build_set_relay_code_len(self, seconds: int, pw: int = 0) -> bytes:
        """设置转发中继引导码长值 (AFN=1CH)，1B BIN，0~255 s（§7.2.12）。"""
        if not 0 <= seconds <= 255:
            raise EncodeError(f"中继引导码长值超范围(0~255 s): {seconds}")
        return self.build_param_set_frame(0x1C, 0x00, bytes([seconds]), pw)

    def build_set_relay_addr(self, addr_list: list[bytes], pw: int = 0) -> bytes:
        """设置中继站转发监测站地址 (AFN=1DH)，N×5B（格式同地址域，§7.2.13）。"""
        data = bytearray()
        for a in addr_list:
            if len(a) != 5:
                raise EncodeError(f"转发地址必须为 5 字节，当前 {len(a)} 字节")
            data.extend(a)
        return self.build_param_set_frame(0x1D, 0x00, bytes(data), pw)

    def build_set_relay_auto_switch(self, value: int, pw: int = 0) -> bytes:
        """设置中继站工作机自动切换/自报状态 (AFN=1EH)，1B BIN（§7.2.14）。"""
        if not 0 <= value <= 0xFF:
            raise EncodeError(f"中继自动切换状态字节超范围(0~0xFF): {value}")
        return self.build_param_set_frame(0x1E, 0x00, bytes([value]), pw)

    def build_set_flow_limits(
        self, points: list[tuple[float, bool]], pw: int = 0
    ) -> bytes:
        """设置流量参数上限值 (AFN=1FH)，每点 5B BCD（表20）。

        points: [(value, unit_hour), ...]
          value: -999999.999~999999.999（m³/s 或 m³/h）
          unit_hour: True=m³/h, False=m³/s
        """
        data = bytearray()
        for value, unit_hour in points:
            if not -999999.999 <= value <= 999999.999:
                raise EncodeError(f"流量上限值超范围(±999999.999): {value}")
            v = int(round(abs(value) * 1000))
            if v > 999999999:
                raise EncodeError(f"流量上限值超范围: {value}")
            b = bytearray(_bcd_le(v, 5))
            high = 0
            if value < 0:
                high |= 0xC0  # D7D6 = 11B 负
            if unit_hour:
                high |= 0x30  # D5D4 = 11B m³/h
            b[4] |= high
            data.extend(b)
        return self.build_param_set_frame(0x1F, 0x00, bytes(data), pw)

    # ------------------------------------------------------------------
    # 参数查询便捷方法 (AFN=50H~65H，规约 7.3.2~7.3.21)
    # 查询帧无附加信息域（AUX），结束符 16H
    # ------------------------------------------------------------------

    def build_query(self, afn: int, data: bytes = b"", func_code: int = 0) -> bytes:
        """通用查询帧（下行，无 PW/Tp）。"""
        ctrl = C.make_ctrl(dir_=0, func_code=func_code)
        return self.build_frame(afn, ctrl, data)

    def build_query_addr(self) -> bytes:
        """查询站点地址 (AFN=50H)。"""
        return self.build_query(0x50)

    def build_query_clock(self) -> bytes:
        """查询站点时钟 (AFN=51H)。"""
        return self.build_query(0x51)

    def build_query_work_mode(self) -> bytes:
        """查询工作模式 (AFN=52H)。"""
        return self.build_query(0x52)

    def build_query_report_kinds(self) -> bytes:
        """查询数据自报种类及时间间隔 (AFN=53H)。"""
        return self.build_query(0x53)

    def build_query_realtime_kinds(self) -> bytes:
        """查询需查询的实时数据种类 (AFN=54H)。"""
        return self.build_query(0x54)

    def build_query_recharge(self) -> bytes:
        """查询最近充值量及剩余水量 (AFN=55H)。"""
        return self.build_query(0x55)

    def build_query_remaining_alarm(self) -> bytes:
        """查询剩余水量及报警值 (AFN=56H)。"""
        return self.build_query(0x56)

    def build_query_event_record(self) -> bytes:
        """查询事件记录 (AFN=5DH)。"""
        return self.build_query(0x5D)

    def build_query_status_alarm(self) -> bytes:
        """查询状态和报警状态 (AFN=5EH)。"""
        return self.build_query(0x5E)

    def build_query_pump_data(self) -> bytes:
        """查询水泵电机实时工作数据 (AFN=5FH)。"""
        return self.build_query(0x5F)

    def build_query_relay_code_len(self) -> bytes:
        """查询转发中继引导码长值 (AFN=60H)。"""
        return self.build_query(0x60)

    def build_query_image(self, image_no: int) -> bytes:
        """查询实时图像 (AFN=61H)，数据域 1B 图片编号（§7.3.17）。"""
        if not 0 <= image_no <= 0xFF:
            raise EncodeError(f"图片编号超范围(0~255): {image_no}")
        return self.build_query(0x61, bytes([image_no]))

    def build_query_relay_addr(self) -> bytes:
        """查询中继站转发监测站地址 (AFN=62H)。"""
        return self.build_query(0x62)

    def build_query_relay_status(self) -> bytes:
        """查询中继站状态和切换记录 (AFN=63H)。"""
        return self.build_query(0x63)

    def build_query_flow_limits(self) -> bytes:
        """查询流量参数上限值 (AFN=64H)。"""
        return self.build_query(0x64)

    def build_query_channel(self) -> bytes:
        """查询主备信道类型及中心站地址 (AFN=65H)。"""
        return self.build_query(0x65)

    def build_query_history_daily(self) -> bytes:
        """查询终端机历史日记录 (AFN=5CH)。

        注：所提供的 SL427-2021 规约文本/PDF 正文未给出 5CH 响应字段定义
        （仅前言提及），故仅实现查询帧；响应暂以字节摘要显示。
        """
        return self.build_query(0x5C)

    # ------------------------------------------------------------------
    # 控制命令 (AFN=90H~96H，规约 7.4，AUX=PW+Tp)
    # ------------------------------------------------------------------

    def build_reset(self, factory_reset: bool = False, pw: int = 0) -> bytes:
        """复位终端参数和状态 (AFN=90H)。factory_reset=True 恢复出厂默认值（§7.4.2）。"""
        code = 0x02 if factory_reset else 0x01
        return self.build_param_set_frame(0x90, 0x00, bytes([code]), pw)

    def build_clear_history(
        self, rain: bool = False, level: bool = False, water: bool = False,
        pw: int = 0,
    ) -> bytes:
        """清空历史数据单元 (AFN=91H)。D0雨量/D1水位/D2水量（§7.4.3）。"""
        mask = (1 if rain else 0) | (2 if level else 0) | (4 if water else 0)
        return self.build_param_set_frame(0x91, 0x00, bytes([mask]), pw)

    def _pump_cmd(self, afn: int, code: int, is_valve: bool, pw: int) -> bytes:
        if not 0 <= code <= 15:
            raise EncodeError(f"水泵/阀门编号超范围(0~15): {code}")
        b = (code & 0x0F) | (0xF0 if is_valve else 0x00)
        return self.build_param_set_frame(afn, 0x00, bytes([b]), pw)

    def build_start_pump(self, code: int, is_valve: bool = False, pw: int = 0) -> bytes:
        """启动水泵或阀门/闸门 (AFN=92H，§7.4.4)。"""
        return self._pump_cmd(0x92, code, is_valve, pw)

    def build_stop_pump(self, code: int, is_valve: bool = False, pw: int = 0) -> bytes:
        """关闭水泵或阀门/闸门 (AFN=93H，§7.4.5)。"""
        return self._pump_cmd(0x93, code, is_valve, pw)

    def _switch_machine(self, afn: int, machine: str, pw: int) -> bytes:
        m = machine.upper()
        if m not in ("A", "B"):
            raise EncodeError(f"值班机只能为 'A'/'B': {machine!r}")
        low = 0x09 if m == "A" else 0x06
        return self.build_param_set_frame(afn, 0x00, bytes([0xA0 | low]), pw)

    def build_switch_comm(self, machine: str = "A", pw: int = 0) -> bytes:
        """切换监测站/中继站通信机 (AFN=94H，§7.4.6)。"""
        return self._switch_machine(0x94, machine, pw)

    def build_switch_relay_work(self, machine: str = "A", pw: int = 0) -> bytes:
        """切换中继站工作机 (AFN=95H，§7.4.7)。"""
        return self._switch_machine(0x95, machine, pw)

    def build_change_password(self, password: int, pw: int = 0) -> bytes:
        """修改监测终端机密码 (AFN=96H)，2B BCD 小端（表51，§7.4.8）。"""
        if not 0 <= password <= 9999:
            raise EncodeError(f"密码超范围(0~9999): {password}")
        return self.build_param_set_frame(0x96, 0x00, _bcd_le(password, 2), pw)

    # ------------------------------------------------------------------
    # 配置 (AFN=A0H~A2H，规约 7.2.22~7.2.24，AUX=PW+Tp)
    # ------------------------------------------------------------------

    def build_set_realtime_kinds(self, mask: int, pw: int = 0) -> bytes:
        """设置需查询的实时数据种类 (AFN=A0H)，2B BIN 位图（表23）。"""
        if not 0 <= mask <= 0xFFFF:
            raise EncodeError(f"实时数据种类位图超范围(0~0xFFFF): {mask}")
        return self.build_param_set_frame(0xA0, 0x00, mask.to_bytes(2, "little"), pw)

    def build_set_report_kinds(
        self, mask: int, intervals: list[int], pw: int = 0
    ) -> bytes:
        """设置数据自报种类及时间间隔 (AFN=A1H)，2B 位图 + N×2B BCD 间隔（表24/25）。

        intervals: 按参数顺序的自报间隔(min)，每项 1~9999；长度 ≤15。
        """
        if not 0 <= mask <= 0xFFFF:
            raise EncodeError(f"自报种类位图超范围(0~0xFFFF): {mask}")
        if len(intervals) > 15:
            raise EncodeError(f"自报间隔最多 15 项，当前 {len(intervals)}")
        data = bytearray(mask.to_bytes(2, "little"))
        for iv in intervals:
            if not 1 <= iv <= 9999:
                raise EncodeError(f"自报间隔超范围(1~9999 min): {iv}")
            data.extend(_bcd_le(iv, 2))
        return self.build_param_set_frame(0xA1, 0x00, bytes(data), pw)

    def build_set_channel(
        self, main_type: int, main_addr: bytes,
        backup_type: int = 0xAA, backup_addr: bytes = b"\xAA", pw: int = 0,
    ) -> bytes:
        """设置主备信道类型及中心站地址 (AFN=A2H，§7.2.24）。

        main_type/backup_type: 01短信/02IPV4/03北斗；无备用信道时 backup_type=0xAA,
        backup_addr=b"\\xAA"（合计 0xAAAA）。
        地址码长度由类型码决定（规约 7.2.24 c/表26）：短信 7B BCD、IPV4 7B HEX、
        北斗 3B BCD；无备用信道地址码为 1B（0xAA）。
        """
        if not 0 <= main_type <= 0xFF or not 0 <= backup_type <= 0xFF:
            raise EncodeError("信道类型码超范围(0~0xFF)")

        def _check_addr_len(type_code: int, addr: bytes, which: str) -> None:
            if type_code == 0xAA:
                if len(addr) != 1:
                    raise EncodeError(
                        f"{which}无备用信道时地址码应为 1 字节 0xAA，"
                        f"当前 {len(addr)} 字节")
                return
            n = {0x01: 7, 0x02: 7, 0x03: 3}.get(type_code)
            if n is not None and len(addr) != n:
                raise EncodeError(
                    f"{which}类型码 0x{type_code:02X} 地址码应为 {n} 字节，"
                    f"当前 {len(addr)} 字节")

        _check_addr_len(main_type, main_addr, "主信道")
        _check_addr_len(backup_type, backup_addr, "备用信道")
        data = bytes([main_type]) + bytes(main_addr) + \
            bytes([backup_type]) + bytes(backup_addr)
        return self.build_param_set_frame(0xA2, 0x00, data, pw)

    def build_set_report_threshold(
        self, category: int, index: int, interval_min: int,
        threshold: float, pw: int = 0,
    ) -> bytes:
        """设置监测参数启报阈值及固态存储间隔 (AFN=20H，§7.2.16）。

        category: 参数类别 BIN(0~15，表21)；index: 同类参数编号(0~15)
        interval_min: 固态存储间隔 1~255 min
        threshold: 雨量启报阈值 0.1~9.9 mm（1B BCD，低位在前）
        """
        if not 0 <= category <= 15:
            raise EncodeError(f"参数类别超范围(0~15): {category}")
        if not 0 <= index <= 15:
            raise EncodeError(f"参数编号超范围(0~15): {index}")
        if not 1 <= interval_min <= 255:
            raise EncodeError(f"固态存储间隔超范围(1~255 min): {interval_min}")
        if not 0.1 <= threshold <= 9.9:
            raise EncodeError(f"雨量启报阈值超范围(0.1~9.9 mm): {threshold}")
        byte1 = ((category & 0x0F) << 4) | (index & 0x0F)
        data = bytes([byte1, interval_min, _bcd_byte(int(round(threshold * 10)))])
        return self.build_param_set_frame(0x20, 0x00, data, pw)
