# sl427 — SL427-2021 水资源监测数据传输规约

## 概述

基于 IEC 60870-5-101 帧结构（68H 起始）的 SL/T 427-2021 水资源监测数据传输规约实现。

## 文件清单

| 文件 | 说明 |
|------|------|
| `constants.py` | 协议常量：AFN 表（30 项）、控制功能码表（16 种）、告警/终端状态位、`parse_ctrl`/`make_ctrl` |
| `decoder.py` | 68H 帧解析器：CRC8 校验、AUX 分离、按 AFN+命令类型码分派数据解析 |
| `encoder.py` | 68H 帧编码器：自报 5 类 + 参数设置 6 类 + 通用模板 |

## 核心 API

### `SL427Decoder`

```python
from sl427 import SL427Decoder

decoder = SL427Decoder()
r = decoder.decode_hex("681568...")  # hex 字符串
r = decoder.decode(frame_bytes)      # bytes
```

**返回**: `DecodedMessage` 数据类，主要字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `direction` | `str` | 上下行标签 |
| `ctrl_func_name` | `str` | 命令与类型码名称 |
| `addr_display` | `str` | 地址域格式化展示 |
| `afn` | `int` | AFN 功能码 |
| `afn_name` | `str` | AFN 功能码名称 |
| `crc_ok` | `bool` | CRC8 校验结果 |
| `elements` | `list[ElementValue]` | 要素列表 |
| `special_info` | `dict` | 特殊信息（心跳类型、图像数据等） |
| `to_dict()` | `dict` | 转为字典 |

### `SL427Encoder`

```python
from sl427 import SL427Encoder, encode_address

addr = encode_address(method=1, admin_code=110108, stn_id=1284)
enc = SL427Encoder(addr)
```

**上行帧方法**:

| 方法 | AFN | 说明 |
|------|-----|------|
| `build_heartbeat(hb_type=0xF2)` | 0x02 | 链路检测（F0登录/F1退出/F2在线保持） |
| `build_self_report_c0(func_code, data, tp, alarm, state)` | 0xC0 | 自报实时数据 |
| `build_self_report_81(func_code, data, tp, alarm, state)` | 0x81 | 自报告警 |
| `build_self_report_82(func_code, data, tp, alarm, state)` | 0x82 | 人工置数 |
| `build_self_report_84(voltage, tp)` | 0x84 | 自报电压 |
| `build_query_response(func_code, data)` | 0xB0 | 查询响应 |

**下行帧方法**:

| 方法 | AFN | 说明 |
|------|-----|------|
| `build_set_addr(new_addr_bytes, pw)` | 0x10 | 设置站址 |
| `build_set_clock(dt, pw)` | 0x11 | 设置时钟（含星期月复合字节） |
| `build_set_work_mode(mode, pw)` | 0x12 | 设置工作模式 |
| `build_set_recharge(amount, pw)` | 0x15 | 设置充值量 |
| `build_set_ic_card_on(pw)` | 0x30 | IC卡功能有效 |
| `build_set_ic_card_off(pw)` | 0x31 | 取消IC卡功能 |
| `build_param_set_frame(afn, func_code, data, pw, tp)` | 10~4F | 通用参数设置模板 |

### 辅助函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `make_ctrl` | `(dir_, func_code, div=0, fcb=0) -> int` | 构造控制域字节 C |
| `encode_address` | `(method=1, admin_code=0, stn_id=1, hex_code="") -> bytes` | 编码 5B 地址域 |
| `encode_tp` | `(dt=None, delay=0) -> bytes` | 编码 7B 时间标签 |
| `parse_ctrl` | `(c: int) -> dict` | 解析控制域字节 C |

## 依赖

- `sl651/bcd.py` — BCD 编解码、bytes↔hex
- `sl651/crc.py` — CRC8
- 无外部依赖

## 使用示例

```python
from sl427 import SL427Decoder, SL427Encoder, make_ctrl, encode_address, encode_tp
from datetime import datetime

# === 解码 ===
r = SL427Decoder().decode_hex("681568B40102030405C05545040020700030151412052600AD16")
print(r.afn_name, r.direction)
for e in r.elements:
    print(f"  {e.name}: {e.value} {e.unit}")

# === 编码 ===
addr = encode_address(method=1, admin_code=110108, stn_id=1284)
enc = SL427Encoder(addr)
f = enc.build_heartbeat()  # 链路检测
f = enc.build_self_report_c0(func_code=0x02, data=wl_bytes, tp=datetime.now())
f = enc.build_set_clock(datetime.now())  # 下行校时

# === 控制域构造 ===
ctrl = make_ctrl(dir_=1, func_code=0x02)    # 上行，命令=水位
ctrl = make_ctrl(dir_=0, func_code=0x00)    # 下行，命令=确认
```
