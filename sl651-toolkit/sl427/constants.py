"""SL427-2021 水资源监测数据传输规约 常量定义。

帧结构（表3）:

    68 L 68 | C | A(5B) | AFN | D [| PW(2B)] [| Tp(7B)] | CS(CRC8) | 16

地址域A（6.3.3.4）:
    方式1: A1=3B BCD(行政区划码) + A2=2B BIN(站址,小端)
    方式2: BYTE1=00H + BYTE2~5=8位HEX监测站编码(nibble-packed)

Tp时间标签（6.3.3.8）:
    前6字节: 秒分时日月年 BCD
    第7字节: 允许发送传输延时时长 BIN 单位min

CRC8: 多项式 X7+X6+X5+X2+1 (0xE5) 初值0
"""

from __future__ import annotations

START_BYTE = 0x68
END_BYTE = 0x16

AFN_MAP: dict[int, str] = {
    # 链路检测
    0x02: "链路检测（心跳）",
    # 参数设置 (10H~4FH, 下行, AUX=PW+Tp)
    0x10: "设置地址 (5B)",
    0x11: "设置时钟 (6B BCD)",
    0x12: "设置工作模式 (1B)",
    0x15: "设置充值量 (4B BCD)",
    0x16: "设置剩余水量报警值 (3B BCD)",
    0x17: "设置水位基值/上下限 (N×7B BCD)",
    0x18: "设置水压上下限 (N×8B BCD)",
    0x19: "设置水质参数种类及上限 (5+N×4B)",
    0x1A: "设置水质参数种类及下限 (5+N×4B)",
    0x1B: "设置水量初始值 (N×5B BCD)",
    0x1C: "设置中继引导码长值 (1B BIN)",
    0x1D: "设置中继站转发地址 (N×5B BIN)",
    0x1E: "设置中继站自动切换/自报 (1B BIN)",
    0x1F: "设置流量参数上限值 (N×5B BCD)",
    0x20: "设置启报阈值及固态存储间隔",
    0x30: "IC卡功能有效",
    0x31: "取消IC卡功能",
    0x32: "定值控制投入",
    0x33: "定值控制退出",
    0x34: "定值量设定 (5B BCD)",
    # 参数查询 (50H~9FH)
    0x50: "查询地址",
    0x61: "查询实时图像",
    0xB0: "查询/实时值（响应）",
    # 自报数据 (C0H~)
    0xC0: "自报实时数据",
    0x81: "自报告警数据",
    0x82: "人工置数",
    0x83: "自报图片数据",
    0x84: "自报电压数据",
    # 其他
    0xFF: "用户自定义",
}

# AFN 数据域字节数（仅固定长度或无命令帧）
AFN_DATA_LEN: dict[int, int | None] = {
    0x10: 5,    # 设置地址: 5B
    0x11: 6,    # 设置时钟: 6B BCD
    0x12: 1,    # 设置工作模式: 1B
    0x15: 4,    # 设置充值量: 4B BCD
    0x16: 3,    # 设置剩余水量报警值: 3B BCD
    0x1C: 1,    # 中继引导码长值: 1B
    0x1E: 1,    # 中继自动切换: 1B
    0x30: 0,    # IC卡有效: 无数据域
    0x31: 0,    # 取消IC卡: 无数据域
    0x32: 0,    # 定值控制投入: 无数据域
    0x33: 0,    # 定值控制退出: 无数据域
    0x34: 5,    # 定值量设定: 5B BCD
}

HEART_MAP: dict[int, str] = {
    0xF0: "登录",
    0xF1: "退出登录",
    0xF2: "在线保持",
}

CTRL_FUNC_MAP: dict[int, dict] = {
    0x00: {"name": "确认/应答", "byteLen": 0, "decimal": 0, "signed": False, "array": False, "unit": ""},
    0x01: {"name": "雨量", "byteLen": 3, "decimal": 1, "signed": False, "array": False, "unit": "mm"},
    0x02: {"name": "水位", "byteLen": 4, "decimal": 3, "signed": True, "array": True, "unit": "m"},
    0x03: {"name": "流量/水量", "byteLen": 5, "decimal": 3, "signed": True, "array": True, "unit": "m³/s"},
    0x04: {"name": "流速", "byteLen": 3, "decimal": 3, "signed": True, "array": True, "unit": "m/s"},
    0x05: {"name": "闸位", "byteLen": 3, "decimal": 2, "signed": False, "array": False, "unit": "m"},
    0x06: {"name": "功率", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "kW"},
    0x07: {"name": "气象参数", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": ""},
    0x08: {"name": "电量参数", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": ""},
    0x09: {"name": "水温", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "°C"},
    0x0A: {"name": "水质", "byteLen": 3, "decimal": 0, "signed": True, "array": True, "unit": ""},
    0x0B: {"name": "土壤含水率", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "%"},
    0x0C: {"name": "蒸发量", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "mm"},
    0x0D: {"name": "电压", "byteLen": 2, "decimal": 2, "signed": False, "array": False, "unit": "V"},
    # 注: 0x0D 在规约不同上下文中含义不同
    #   下行: 报警或状态参数 (表6)
    #   上行: 统计雨量 (7.5.6 c)  
    #   AFN=84H: 电压 (表B.98, 沿用 njnrs 标签)
    0x0E: {"name": "综合参数", "byteLen": 1, "decimal": 0, "signed": False, "array": False, "unit": ""},
    0x0F: {"name": "水压", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "MPa"},
}

COMP_BITS = [0x0A, 0x0B, 0x06, 0x07, 0x05, 0x03, 0x02, 0x01]

ALARM_BITS = [
    {"bit": 0, "name": "工作交流电停电告警", "map": {0: "正常", 1: "停电"}},
    {"bit": 1, "name": "蓄电池电压报警", "map": {0: "正常", 1: "电压低"}},
    {"bit": 2, "name": "水位超限报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 3, "name": "流量超限报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 4, "name": "水质超限报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 5, "name": "流量仪表故障报警", "map": {0: "正常", 1: "故障"}},
    {"bit": 6, "name": "水泵开停状态", "map": {0: "水泵工作", 1: "水泵停机"}},
    {"bit": 7, "name": "水位仪表故障报警", "map": {0: "正常", 1: "故障"}},
    {"bit": 8, "name": "水压超限报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 9, "name": "温度超限报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 10, "name": "终端IC卡功能报警", "map": {0: "正常", 1: "IC卡有效"}},
    {"bit": 11, "name": "定值控制报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 12, "name": "剩余水量下限报警", "map": {0: "未超限", 1: "超限"}},
    {"bit": 13, "name": "终端箱门状态报警", "map": {0: "关闭", 1: "开启"}},
]

TERMINAL_BITS = [
    {"bit": [0, 1], "name": "终端工作模式", "map": {0: "自报/遥测", 1: "自报确认", 2: "遥测", 3: "调试/维修"}},
    {"bit": 2, "name": "IC卡功能有效", "map": {0: "无效", 1: "有效"}},
    {"bit": 3, "name": "定值控制投入", "map": {0: "退出", 1: "投入"}},
    {"bit": 4, "name": "水泵工作状态", "map": {0: "开启", 1: "关闭"}},
    {"bit": 5, "name": "终端箱门状态", "map": {0: "开启", 1: "关闭"}},
    {"bit": 6, "name": "电源工作状态", "map": {0: "AC220V供电", 1: "蓄电池供电"}},
]

# AFN 类别：无AUX / 仅Tp / PW+Tp
AFN_NO_AUX = {0x02}
AFN_TP_ONLY = {0xC0, 0x81, 0x82, 0xFF}  # 0x83/0x84 按 B.96/B.98 不含 Tp
AFN_PW_TP = {0x10, 0x11}  # 参数设置类

TP_LEN = 7
PW_LEN = 2


def parse_ctrl(c: int) -> dict:
    """解析控制域字节 C（表4）。"""
    return {
        "dir": (c >> 7) & 1,
        "div": (c >> 6) & 1,
        "fcb": (c >> 4) & 0x03,
        "func_code": c & 0x0F,
    }


def make_ctrl(dir_: int, func_code: int, div: int = 0, fcb: int = 0) -> int:
    """构造控制域字节 C。"""
    return ((dir_ & 1) << 7) | ((div & 1) << 6) | ((fcb & 3) << 4) | (func_code & 0x0F)


def encode_pw(key1: int, key2: int) -> bytes:
    """构造密码 PW（2B），按规范表9。
    key1: 1 位 BCD(0~9), 密钥1, 放在 PW 第1字节高半字节
    key2: 3 位 BCD(0~999), 密钥2, 放在 PW 第1字节低半字节 + 第2字节
    """
    if not 0 <= key1 <= 9:
        raise ValueError(f"PW key1 超出范围: {key1} (0~9)")
    if not 0 <= key2 <= 999:
        raise ValueError(f"PW key2 超出范围: {key2} (0~999)")
    from sl651.bcd import int_to_bcd
    byte1 = (key1 << 4) | (key2 // 100)
    byte2 = int_to_bcd(key2 % 100)
    return bytes([byte1, byte2])
