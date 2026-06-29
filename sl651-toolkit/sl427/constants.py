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
    0x02: "链路检测（心跳）",
    0x10: "设置地址",
    0x11: "设置时钟",
    0xC0: "自报实时数据",
    0xB0: "查询/实时值",
    0x61: "图像数据",
    0x81: "自报告警数据",
    0x82: "人工置数",
    0x83: "自报图片数据",
    0x84: "自报电压数据",
    0xFF: "用户自定义",
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
    0x07: {"name": "气压", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "hPa"},
    0x08: {"name": "风速", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "m/s"},
    0x09: {"name": "水温", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "°C"},
    0x0A: {"name": "水质", "byteLen": 3, "decimal": 0, "signed": True, "array": True, "unit": ""},
    0x0B: {"name": "土壤含水率", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "%"},
    0x0C: {"name": "蒸发量", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "mm"},
    0x0D: {"name": "电压", "byteLen": 2, "decimal": 2, "signed": False, "array": False, "unit": "V"},
    0x0E: {"name": "综合参数", "byteLen": 1, "decimal": 0, "signed": False, "array": False, "unit": ""},
    0x0F: {"name": "水压", "byteLen": 3, "decimal": 0, "signed": False, "array": False, "unit": "MPa"},
}

COMP_BITS = [0x0A, 0x0B, 0x06, 0x08, 0x05, 0x03, 0x02, 0x01]

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
    {"bit": 10, "name": "终端IC卡功能报警", "map": {0: "正常", 1: "IC卡有效"}},
    {"bit": 11, "name": "定值控制报警", "map": {0: "正常", 1: "报警"}},
    {"bit": 12, "name": "剩余水量下限报警", "map": {0: "未超限", 1: "超限"}},
    {"bit": 13, "name": "终端箱门状态报警", "map": {0: "关闭", 1: "开启"}},
]

TERMINAL_BITS = [
    {"bit": [0, 1], "name": "终端工作模式", "map": {0: "自报/遥测", 1: "自报确认", 2: "遥测", 3: "调试/维修"}},
    {"bit": 2, "name": "IC卡功能有效", "map": {0: "开启", 1: "关闭"}},
    {"bit": 3, "name": "定值控制投入", "map": {0: "开启", 1: "关闭"}},
    {"bit": 4, "name": "水泵工作状态", "map": {0: "开启", 1: "关闭"}},
    {"bit": 5, "name": "终端箱门状态", "map": {0: "开启", 1: "关闭"}},
    {"bit": 6, "name": "电源工作状态", "map": {0: "AC220V供电", 1: "蓄电池供电"}},
]

# AFN 类别：无AUX / 仅Tp / PW+Tp
AFN_NO_AUX = {0x02}
AFN_TP_ONLY = {0xC0, 0x81, 0x82, 0x83, 0x84, 0xFF}
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
