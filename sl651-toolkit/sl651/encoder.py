"""SL651-2014 报文编码器。"""

from __future__ import annotations

from datetime import datetime

from . import constants as C
from .bcd import (
    datetime_to_bcd,
    int_to_bcd_bytes,
)
from .crc import crc16


class EncodeError(Exception):
    """编码异常。"""


def _make_def_byte(data_len: int, decimals: int = 0) -> int:
    if not 0 <= data_len <= 31:
        raise EncodeError(f"数据字节数超范围(0~31): {data_len}")
    if not 0 <= decimals <= 7:
        raise EncodeError(f"小数位数超范围(0~7): {decimals}")
    return ((data_len & 0x1F) << 3) | (decimals & 0x07)


def _check_datetime(value: datetime, name: str) -> None:
    """时间参数类型校验，非 datetime 抛 EncodeError。"""
    if not isinstance(value, datetime):
        raise EncodeError(f"{name} 必须为 datetime，实际 {type(value).__name__}")


def _encode_bcd(value: float, data_len: int, decimals: int) -> bytes:
    """浮点数 -> BCD 编码字节。负数按 SL651 6.6.3.3 用 0xFF 前缀。"""
    negative = value < 0
    if negative and data_len < 2:
        raise EncodeError(f"负数编码至少需要 2 字节（0xFF 前缀 + 数据），当前 data_len={data_len}")
    scaled = round(abs(value) * (10 ** decimals))
    try:
        if negative:
            bcd = int_to_bcd_bytes(scaled, data_len - 1)
            return b"\xFF" + bcd
        return int_to_bcd_bytes(scaled, data_len)
    except ValueError as e:
        raise EncodeError(
            f"BCD 值超范围 (value={value}, data_len={data_len}, decimals={decimals}): {e}"
        ) from e


class SL651Encoder:
    """SL651 报文编码器。

    password 默认 0 用于测试；生产环境应使用 SL651 规范要求的非零密码。
    """

    def __init__(
        self,
        center_addr: int = 1,
        station_addr: str = "0000000000",
        password: int = 0,
        station_type: int = 0x4B,
    ):
        if not 1 <= center_addr <= 254:
            raise EncodeError(f"center_addr 超范围(1~254): {center_addr}")
        self.center_addr = center_addr
        self.station_addr_hex = station_addr
        if len(station_addr) != 10:
            raise EncodeError(f"station_addr 必须为 10 位十六进制字符串，当前: {station_addr!r}")
        try:
            self.station_addr_bytes = bytes.fromhex(station_addr)
        except ValueError:
            raise EncodeError(f"station_addr 不是有效 hex: {station_addr!r}")
        if not 0 <= password <= 0xFFFF:
            raise EncodeError(f"password 超范围(0~0xFFFF): {password}")
        if not 0 <= station_type <= 0xFF:
            raise EncodeError(f"station_type 超范围(0~0xFF): {station_type}")
        self.password = password
        self.station_type = station_type
        self._serial = int(datetime.now().timestamp()) % 65535 + 1


    def build_frame(
        self,
        function_code: int,
        body: bytes,
        direction: int = C.DIR_UPLINK,
        ascii_mode: bool = False,  # 已废弃（旧双 SOH 方言），请使用 build_ascii_frame
        end_marker: int | None = None,
        tx_time: datetime | None = None,
    ) -> bytes:
        """构造完整 SL651 帧。

        ascii_mode=True 时使用 SOH(01H) 起始符（ASCⅡ编码）。
        end_marker: 报文结束符，上行默认 ETX(03H)，下行按帧类型选 ENQ/ACK/EOT/NAK/ESC。
        tx_time: 发报时间，默认当前时间。下行 4AH 校时帧传此值作为校时时钟。
        """
        if not 0 <= function_code <= 0xFF:
            raise EncodeError(f"function_code 超范围(0~0xFF): {function_code}")
        if end_marker is None:
            end_marker = C.ETX

        is_downlink = direction == C.DIR_DOWNLINK
        if tx_time is not None:
            _check_datetime(tx_time, "tx_time")
            actual_tx_time = datetime_to_bcd(tx_time)
        else:
            actual_tx_time = datetime_to_bcd(datetime.now())

        if is_downlink:
            serial = 0
        elif function_code == 0x2F:
            serial = self._serial
        else:
            self._serial = (self._serial % 65535) + 1
            serial = self._serial

        body_len = C.SERIAL_LEN + C.TX_TIME_LEN + len(body)
        if body_len > 4095:
            raise EncodeError(
                f"正文长度超范围(报文标识仅 12 位, ≤4095 字节): {body_len}"
            )
        ident_hi = (direction << 7) | ((body_len >> 8) & 0x0F)
        ident_lo = body_len & 0xFF

        header_body = bytearray()
        # 表11(上行): [中心][站址]; 表12(下行): [站址][中心]
        if direction == C.DIR_UPLINK:
            header_body.append(self.center_addr)
            header_body.extend(self.station_addr_bytes)
        else:
            header_body.extend(self.station_addr_bytes)
            header_body.append(self.center_addr)
        header_body.append((self.password >> 8) & 0xFF)
        header_body.append(self.password & 0xFF)
        header_body.append(function_code)
        header_body.append(ident_hi)
        header_body.append(ident_lo)
        header_body.append(C.STX)
        header_body.append((serial >> 8) & 0xFF)
        header_body.append(serial & 0xFF)
        header_body.extend(actual_tx_time)
        header_body.extend(body)
        header_body.append(end_marker)

        start_byte = C.SOH if ascii_mode else C.START_BYTE
        frame_body = bytes([start_byte, start_byte]) + bytes(header_body)
        crc = crc16(frame_body)
        header_body.append((crc >> 8) & 0xFF)
        header_body.append(crc & 0xFF)

        return bytes([start_byte, start_byte]) + bytes(header_body)

    def build_timing_body(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
    ) -> bytes:
        """构造上行定时报正文。

        elements: [(引导符, 值, 数据字节数, 小数位数), ...]
        """
        if obs_time is None:
            obs_time = datetime.now()
        _check_datetime(obs_time, "obs_time")
        ot = datetime_to_bcd(obs_time)[:5]

        body = bytearray()
        body.append(0xF1)
        body.append(0xF1)
        body.extend(self.station_addr_bytes)
        body.append(self.station_type)
        body.append(0xF0)
        body.append(0xF0)
        body.extend(ot)

        for guide, value, data_len, decimals in elements:
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))

        return bytes(body)

    def build_timing_frame(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
        function_code: int = 0x32,
    ) -> bytes:
        body = self.build_timing_body(elements, obs_time)
        return self.build_frame(function_code, body)

    def build_test_frame(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
    ) -> bytes:
        """测试报 (0x30)。正文结构与定时报相同（规约表28）。"""
        return self.build_timing_frame(elements, obs_time, function_code=0x30)

    def build_link_maintain_body(self) -> bytes:
        return b""

    def build_link_maintain_frame(self) -> bytes:
        return self.build_frame(0x2F, self.build_link_maintain_body())

    def build_alarm_body(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
        trigger: tuple[int, float, int, int] | None = None,
    ) -> bytes:
        """构造上行加报报正文。trigger 为触发要素(引导符,值,字节数,小数位)，放在正文首部（表34）。"""
        if obs_time is None:
            obs_time = datetime.now()
        _check_datetime(obs_time, "obs_time")
        ot = datetime_to_bcd(obs_time)[:5]

        body = bytearray()
        body.append(0xF1)
        body.append(0xF1)
        body.extend(self.station_addr_bytes)
        body.append(self.station_type)
        body.append(0xF0)
        body.append(0xF0)
        body.extend(ot)

        if trigger:
            guide, value, data_len, decimals = trigger
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))

        for guide, value, data_len, decimals in elements:
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))

        return bytes(body)

    def build_alarm_frame(
        self,
        elements: list[tuple[int, float, int, int]],
        obs_time: datetime | None = None,
        trigger: tuple[int, float, int, int] | None = None,
    ) -> bytes:
        return self.build_frame(0x33, self.build_alarm_body(elements, obs_time, trigger))

    def build_hourly_body(
        self,
        water_levels: list[float | None],
        inst_level: float,
        voltage: float,
        obs_time: datetime | None = None,
        rain_amounts: list[float | None] | None = None,
    ) -> bytes:
        """构造上行小时报正文。规约 §6.6.4.7 表36 固定 12 组 5min 水位。
        rain_amounts: 可选 12 组 5min 雨量（F4，各 2B，单位 0.1mm）。
        """
        if len(water_levels) != 12:
            raise EncodeError(f"小时报要求恰好 12 组水位，当前 {len(water_levels)} 组")
        if rain_amounts is not None and len(rain_amounts) != 12:
            raise EncodeError(f"小时报雨量要求恰好 12 组，当前 {len(rain_amounts)} 组")
        if obs_time is None:
            obs_time = datetime.now()
        _check_datetime(obs_time, "obs_time")
        ot = datetime_to_bcd(obs_time)[:5]

        body = bytearray()
        body.append(0xF1)
        body.append(0xF1)
        body.extend(self.station_addr_bytes)
        body.append(self.station_type)
        body.append(0xF0)
        body.append(0xF0)
        body.extend(ot)

        if rain_amounts is not None:
            body.append(0xF4)
            body.append(_make_def_byte(12, 0))
            for rn in rain_amounts:
                if rn is None:
                    body.append(0xFF)
                else:
                    val = int(round(rn * 10))
                    if val < 0 or val > 255:
                        body.append(0xFF)
                    else:
                        body.append(val)

        body.append(0xF5)
        body.append(_make_def_byte(24, 2))
        for wl in water_levels:
            if wl is None:
                body.extend(b'\xFF\xFF')
            else:
                val = int(round(wl * 100))
                if val < 0:
                    body.extend(b'\xFF\xFF')
                elif val > 0xFFFF:
                    raise EncodeError(f"小时报水位超范围(最大 655.35m): {wl}")
                else:
                    body.extend(val.to_bytes(2, 'big'))

        body.append(0x39)
        body.append(_make_def_byte(4, 3))
        body.extend(_encode_bcd(inst_level, 4, 3))

        body.append(0x38)
        body.append(_make_def_byte(2, 2))
        body.extend(_encode_bcd(voltage, 2, 2))

        return bytes(body)

    def build_hourly_frame(
        self,
        water_levels: list[float | None],
        inst_level: float,
        voltage: float,
        obs_time: datetime | None = None,
        rain_amounts: list[float | None] | None = None,
    ) -> bytes:
        return self.build_frame(0x34, self.build_hourly_body(water_levels, inst_level, voltage, obs_time, rain_amounts))

    # ------------------------------------------------------------------
    # 下行帧（中心站 → 遥测站）
    # ------------------------------------------------------------------

    def build_query_body(self, element_guides: list[int]) -> bytes:
        """查询指定要素正文（3AH 功能码）：列出要查询的要素引导符+定义符（数据域为空）。"""
        body = bytearray()
        for guide in element_guides:
            body.append(guide)
            body.append(_make_def_byte(0, 0))  # 查询时数据域长度为0
        return bytes(body)

    def build_query_frame(self) -> bytes:
        """查询实时数据帧（下行，0x37，表42：仅流水号+发报时间，结束符 ENQ）。"""
        return self.build_frame(0x37, b"",
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_downlink_query(self, function_code: int) -> bytes:
        """通用下行查询帧：正文仅流水号+发报时间，结束符 ENQ。

        适用于表42/54/56/59/83/85 等无参数体的查询（44H/45H/46H/50H/51H）。
        """
        if not 0 <= function_code <= 0xFF:
            raise EncodeError(f"function_code 超范围(0~0xFF): {function_code}")
        return self.build_frame(function_code, b"",
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_query_pump_data(self) -> bytes:
        """查询水泵电机实时工作数据（下行，0x44，表54）。"""
        return self.build_downlink_query(0x44)

    def build_query_software_version(self) -> bytes:
        """查询遥测站软件版本（下行，0x45，表56）。"""
        return self.build_downlink_query(0x45)

    def build_query_status_alarm(self) -> bytes:
        """查询遥测站状态及报警（下行，0x46，表59）。"""
        return self.build_downlink_query(0x46)

    def build_query_event_record(self) -> bytes:
        """查询遥测站事件记录（下行，0x50，表83）。"""
        return self.build_downlink_query(0x50)

    def build_query_clock(self) -> bytes:
        """查询遥测站时钟（下行，0x51，表85）。"""
        return self.build_downlink_query(0x51)

    def build_set_param_body(self, params: list[tuple[int, float, int, int]]) -> bytes:
        """参数设置正文：引导符+定义符+数据值。"""
        body = bytearray()
        for guide, value, data_len, decimals in params:
            body.append(guide)
            body.append(_make_def_byte(data_len, decimals))
            body.extend(_encode_bcd(value, data_len, decimals))
        return bytes(body)

    def build_set_param_frame(
        self, params: list[tuple[int, float, int, int]], function_code: int = 0x40
    ) -> bytes:
        """参数设置帧（下行，默认 0x40 修改基本配置表；0x42 修改运行参数，结束符 ENQ）。"""
        return self.build_frame(function_code, self.build_set_param_body(params),
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_read_config_frame(
        self, guides: list[int], function_code: int = 0x41
    ) -> bytes:
        """读取基本配置/运行参数帧（下行，默认 0x41；0x43 读取运行参数，结束符 ENQ）。

        正文为待读取参数的标识符列表（引导符+定义符，表52）。
        """
        return self.build_frame(function_code, self.build_query_body(guides),
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_init_solid_storage(self) -> bytes:
        """初始化固态存储数据帧（下行，0x47，表61）。

        正文含 97H「固态存储数据初始化」标识符（附录D #120）。
        """
        return self.build_frame(0x47, bytes([0x97]),
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_change_password_frame(self, old_pw: int, new_pw: int) -> bytes:
        """修改传输密码帧（下行，0x49，表65）。

        正文 = 旧密码(标识符 03H + 2B HEX) + 新密码(标识符 03H + 2B HEX)；
        密码标识符取附录D 表D.1 #3「密码」03H，高位字节在前。
        """
        for name, v in (("旧密码", old_pw), ("新密码", new_pw)):
            if not 0 <= v <= 0xFFFF:
                raise EncodeError(f"{name}超范围(0~0xFFFF): {v}")
        body = (bytes([0x03, (old_pw >> 8) & 0xFF, old_pw & 0xFF])
                + bytes([0x03, (new_pw >> 8) & 0xFF, new_pw & 0xFF]))
        return self.build_frame(0x49, body,
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    def build_manual_frame(self, payload: bytes) -> bytes:
        """人工置数报（上行，0x35）。

        正文 = F2H 人工置数标识符 + 原编码（SL330，结束符 NN 省略）数据（表38/附录C 注c）。
        payload 为调用方按 SL330 约定编码的原始字节。
        """
        if not payload:
            raise EncodeError("人工置数数据不能为空")
        return self.build_frame(0x35, bytes([0xF2]) + bytes(payload))

    def build_clock_sync_body(self, dt: datetime | None = None) -> bytes:
        """时钟校准正文（0x4A 表67）：空，发报时间即校时值。"""
        return b""

    def build_clock_sync_frame(self, dt: datetime | None = None) -> bytes:
        """时钟校准帧 (0x4A, 下行, 结束符 ENQ, 表67)。
        tx_time 直接作为校时时钟值。"""
        return self.build_frame(0x4A, b"",
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ,
                                tx_time=dt)

    def build_reset_body(self) -> bytes:
        """恢复出厂设置正文（表63+D.4#121）：包含 98H 标识符。"""
        return b'\x98'

    def build_reset_frame(self) -> bytes:
        """恢复出厂设置帧 (0x48, 下行, 结束符 ENQ)。"""
        return self.build_frame(0x48, self.build_reset_body(),
                                direction=C.DIR_DOWNLINK, end_marker=C.ENQ)

    # ------------------------------------------------------------------
    # ASCⅡ 编码
    # ------------------------------------------------------------------

    def build_ascii_body(
        self,
        elements: list[tuple[str, str]],
        obs_time: datetime | None = None,
    ) -> bytes:
        """构造 ASCⅡ 编码正文。

        elements: [(ASCⅡ标识符, 值字符串), ...]
        如: [("Z", "12.345"), ("Q", "5.678"), ("VT", "12.6")]
        """
        if obs_time is None:
            obs_time = datetime.now()
        _check_datetime(obs_time, "obs_time")

        parts = []
        parts.append("ST")
        parts.append(self.station_addr_hex)
        parts.append(f"{self.station_type:02X}")
        parts.append("TT")
        parts.append(obs_time.strftime("%y%m%d%H%M"))
        for code, val in elements:
            if code.upper() in ("ST", "TT"):
                raise EncodeError(
                    f"ASCⅡ 标识符 {code!r} 为帧结构保留引导符，不能用作要素标识符"
                )
            parts.append(code)
            parts.append(val)
        parts.append("")

        return " ".join(parts).encode("ascii")

    def build_ascii_frame(
        self,
        elements: list[tuple[str, str]],
        obs_time: datetime | None = None,
        function_code: int = 0x32,
    ) -> bytes:
        """构造 ASCⅡ 编码帧（单 SOH 起始，头部为 ASCII 十六进制字符串，规格表16）。"""
        if obs_time is None:
            obs_time = datetime.now()

        self._serial = (self._serial % 65535) + 1
        serial = self._serial

        actual_tx_time = datetime_to_bcd(datetime.now())

        body_ascii = self.build_ascii_body(elements, obs_time)
        serial_hex = f"{serial:04X}".encode("ascii")
        tx_time_hex = actual_tx_time.hex().upper().encode("ascii")
        body_stx_etx = serial_hex + tx_time_hex + body_ascii

        body_len = C.ASCII_SERIAL_LEN + C.ASCII_TX_TIME_LEN + len(body_ascii)
        if body_len > 4095:
            raise EncodeError(
                f"ASCⅡ 正文长度超范围(报文标识仅 12 位, ≤4095 字节): {body_len}"
            )
        ident_hi = (C.DIR_UPLINK << 7) | ((body_len >> 8) & 0x0F)
        ident_lo = body_len & 0xFF

        frame = bytearray()
        frame.append(C.SOH)
        frame.extend(f"{self.center_addr:02X}".encode("ascii"))
        frame.extend(self.station_addr_hex.encode("ascii"))
        frame.extend(f"{self.password:04X}".encode("ascii"))
        frame.extend(f"{function_code:02X}".encode("ascii"))
        frame.extend(f"{ident_hi:02X}{ident_lo:02X}".encode("ascii"))
        frame.append(C.STX)
        frame.extend(body_stx_etx)
        frame.append(C.ETX)

        crc = crc16(bytes(frame))
        frame.extend(f"{crc:04X}".encode("ascii"))

        return bytes(frame)
