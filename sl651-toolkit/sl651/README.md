# sl651 — SL651-2014 水文监测数据通信规约

## 概述

核心协议库。提供 SL651-2014 报文的编解码能力，支持 HEX/BCD 和 ASCII 两种编码，覆盖上行 7 种 + 下行 4 种功能码。

## 文件清单

| 文件 | 说明 |
|------|------|
| `bcd.py` | BCD 编解码（大端/小端）、时间编解码、hex↔bytes 转换 |
| `crc.py` | CRC-16/MODBUS（0xA001，初值 0xFFFF）、CRC8（0xE5，供 sl427 使用） |
| `constants.py` | 协议常量：101 项 `SL651_ELEMENTS`、102 项 `SL651_ASCII_ELEMENTS`、FF 子标识符、FUNC_MAP（23 项）、STATION_TYPE（11 类）、STATUS_BITS（12 bit）、帧偏移常量 |
| `decoder.py` | 报文解码器：定义符动态解析、ASCII 帧解析、状态位解码、CRC 校验 |
| `encoder.py` | 报文编码器：上行 5 类 + 下行 4 类 + ASCII 编码 + 通用帧构造 |

## 核心 API

### `SL651Decoder`

```python
from sl651 import SL651Decoder

decoder = SL651Decoder()
r = decoder.decode_hex("7E7E...")  # hex 字符串
r = decoder.decode(frame_bytes)    # bytes
```

**返回**: `DecodedMessage` 数据类，主要字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `center_addr` | `str` | 中心站地址 hex |
| `station_addr` | `str` | 遥测站地址 hex |
| `function_code` | `int` | 功能码 |
| `function_name` | `str` | 功能码名称 |
| `message_type` | `str` | 报文类型 |
| `direction_label` | `str` | 上下行标签 |
| `tx_time_display` | `str` | 发报时间（可读格式） |
| `obs_time_display` | `str` | 观测时间（可读格式） |
| `station_type_name` | `str` | 测站类别 |
| `encoding` | `str` | `"BCD"` / `"HEX"` / `"ASCII"` |
| `crc_ok` | `bool` | CRC 校验结果 |
| `elements` | `list[ElementValue]` | 要素列表 |
| `to_dict()` | `dict` | 转为字典 |

**ElementValue**:

| 字段 | 说明 |
|------|------|
| `code` | 要素编码 hex |
| `name` | 要素名称 |
| `value` | 解析值（float/int/str） |
| `unit` | 单位 |
| `raw` | 原始 hex 字符串 |
| `data_type` | `"BCD"` / `"HEX"` / `"ASCII"` / `"STATUS"` / `"F4_ARRAY"` / `"F5_ARRAY"` |

### `SL651Encoder`

```python
from sl651 import SL651Encoder

enc = SL651Encoder(
    center_addr=0x01,
    station_addr="1234567890",
    password=0,
    station_type=0x48,       # 河道站
)
```

| 方法 | 功能码 | 说明 |
|------|--------|------|
| `build_timing_frame(elements, obs_time, function_code=0x32)` | 0x32 | 定时报 |
| `build_alarm_frame(elements, obs_time)` | 0x33 | 加报报 |
| `build_hourly_frame(water_levels, inst_level, voltage, obs_time)` | 0x34 | 小时报（含 12×F5 数组） |
| `build_link_maintain_frame()` | 0x2F | 链路维持 |
| `build_ascii_frame(elements, obs_time)` | 0x32 | ASCII 编码（SOH 起始） |
| `build_query_frame()` | 0x37 | 下行查询所有实时数据（空正文，结束符 ENQ） |
| `build_query_body(element_guides)` | 3AH | 下行查询指定要素（正文含引导符） |
| `build_set_param_frame(params)` | 0x40 | 下行参数设置（结束符 ENQ） |
| `build_clock_sync_frame(dt)` | 0x4A | 下行时钟校准（结束符 ENQ） |
| `build_reset_frame()` | 0x48 | 下行恢复出厂（结束符 ENQ） |
| `build_frame(func, body, direction, ascii_mode, end_marker)` | 任意 | 通用帧构造 |

**elements 格式**: `[(引导符, 值, 数据字节数, 小数位数), ...]`，如 `[(0x39, 12.345, 4, 3)]`

### 辅助函数

| 函数 | 说明 |
|------|------|
| `parse_def_byte(b) -> (data_len, decimals)` | 解析定义符字节 |
| `bcd_to_int(b) -> int` | 单字节 BCD → 整数 |
| `int_to_bcd(v) -> int` | 整数 → 单字节 BCD |
| `bcd_bytes_to_int(data) -> int` | 多字节 BCD → 整数 |
| `bcd_to_datetime(data) -> datetime` | 6B BCD 时间 → datetime |
| `datetime_to_bcd(dt) -> bytes` | datetime → 6B BCD |
| `hex_str_to_bytes(s) -> bytes` | hex 字符串 → bytes |
| `bytes_to_hex(data) -> str` | bytes → hex（带空格分隔） |
| `bytes_to_hex_compact(data) -> str` | bytes → hex（无分隔符） |
| `crc16(data) -> int` | CRC-16/MODBUS |
| `crc8(data) -> int` | CRC8（供 sl427 使用） |

## 依赖

- 无外部依赖（标准库 only）
- 被 `sl427/`、`simulator/`、`tools/` 依赖

## 使用示例

```python
from sl651 import SL651Decoder, SL651Encoder
from datetime import datetime

# === 解码 ===
r = SL651Decoder().decode_hex("7E7E01001234567890......")
print(r.station_addr, r.function_name)
for e in r.elements:
    print(f"  [{e.code}] {e.name}: {e.display_value}")

# === 编码 ===
enc = SL651Encoder(0x01, "1234567890", 0, 0x48)
f = enc.build_timing_frame([(0x39, 12.345, 4, 3)], obs_time=datetime.now())
print(f.hex().upper())
```

## CRC 验证向量

```python
from sl651 import crc16
assert crc16(b"123456789") == 0x4B37  # CRC-16/MODBUS
```
