# sl651 — SL651-2014 水文监测数据通信规约

## 概述

核心协议库。提供 SL651-2014 报文的编解码能力，支持 HEX/BCD 和 ASCII 两种编码。编码器覆盖上行 6 种（2F/30/32/33/34/35）+ 下行 14 种（37/40/41/42/43/44/45/46/47/48/49/4A/50/51），另含 3AH 查询正文构造与多包 SYN/ETB 流式重组。

## 文件清单

| 文件 | 说明 |
|------|------|
| `bcd.py` | BCD 编解码（大端/小端）、时间编解码、hex↔bytes 转换 |
| `crc.py` | CRC-16/MODBUS（0xA001，初值 0xFFFF）、CRC8（0xE5，供 sl427 使用） |
| `constants.py` | 协议常量：101 项 `SL651_ELEMENTS`、102 项 `SL651_ASCII_ELEMENTS`、FF 子标识符、FUNC_MAP（23 项）、STATION_TYPE（11 类）、STATUS_BITS（12 bit）、帧偏移常量 |
| `decoder.py` | 报文解码器：定义符动态解析、ASCII 帧解析、状态位解码、CRC 校验、`feed()` 流式解析与多包 SYN/ETB 重组 |
| `encoder.py` | 报文编码器：上行 6 类 + 下行 14 类 + ASCII 编码 + 通用帧构造 |

## 核心 API

### `SL651Decoder`

```python
from sl651 import SL651Decoder

decoder = SL651Decoder()
r = decoder.decode_hex("7E7E...")  # hex 字符串
r = decoder.decode(frame_bytes)    # bytes

# 流式解析 + 多包 (SYN/ETB) 自动重组（可分多次喂入，支持乱序）
msgs = decoder.feed(chunk_bytes)   # -> list[DecodedMessage]
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
| `warnings` | `list[str]` | 非致命解析告警（如 F4/F5 定义符与规范固定长度不符） |
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
| `build_test_frame(elements, obs_time)` | 0x30 | 测试报（正文同定时报） |
| `build_alarm_frame(elements, obs_time)` | 0x33 | 加报报 |
| `build_hourly_frame(water_levels, inst_level, voltage, obs_time)` | 0x34 | 小时报（含 12×F5 数组） |
| `build_link_maintain_frame()` | 0x2F | 链路维持 |
| `build_ascii_frame(elements, obs_time)` | 0x32 | ASCII 编码（SOH 起始） |
| `build_query_frame()` | 0x37 | 下行查询所有实时数据（空正文，结束符 ENQ） |
| `build_downlink_query(func)` | 任意 | 通用空正文下行查询 |
| `build_query_pump_data/software_version/status_alarm/event_record/clock()` | 44/45/46/50/51 | 无参数体下行查询 |
| `build_query_body(element_guides)` | 3AH | 下行查询指定要素（正文含引导符） |
| `build_manual_frame(payload)` | 0x35 | 人工置数报（F2 标识符 + 原编码） |
| `build_init_solid_storage()` | 0x47 | 初始化固态存储（97H 标识符） |
| `build_change_password_frame(old, new)` | 0x49 | 修改密码（03H 标识符） |
| `build_set_param_frame(params, function_code=0x40)` | 0x40/0x42 | 下行参数设置/修改运行参数（结束符 ENQ） |
| `build_read_config_frame(guides, function_code=0x41)` | 0x41/0x43 | 读取基本配置/运行参数 |
| `build_clock_sync_frame(dt)` | 0x4A | 下行时钟校准（结束符 ENQ） |
| `build_reset_frame()` | 0x48 | 下行恢复出厂（结束符 ENQ） |
| `build_frame(function_code, body, direction, ascii_mode, end_marker, tx_time)` | 任意 | 通用帧构造 |

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
