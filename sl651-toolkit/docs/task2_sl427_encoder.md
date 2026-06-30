# 任务 2：SL427 编码器补全

## 职责边界

在现有 `sl427/encoder.py` 的 `SL427Encoder` 类中，新增自报告警/置数/电压的编码方法，以及参数设置类通用帧。

**不需要做**：
- 不需要修改解码器
- 不需要改 SL651 相关代码
- 不需要读 PDF 规格文档（全部信息在 requirements.md + 源码中）

## 背景知识

### SL427 帧结构

```
68 L 68 | C(1B) | A(5B) | AFN(1B) | D(NB) [| PW(2B)] [| Tp(7B)] | CS(1B CRC8) | 16
```

- CRC8 多项式 `0xE5`，初值 `0x00`，覆盖 C 到 AUX 全部
- `L` = C+A+AFN+D+(PW+Tp) 总字节数，范围 1~255
- 现有 `build_frame()` 已完整实现，新方法只需构造 data + tp 后调用它

### AUX 分类

| AFN 类别 | PW(2B) | Tp(7B) |
|----------|--------|--------|
| 02（链路检测） | 无 | 无 |
| C0/81/82/83/84/FF（自报类） | 无 | 有 |
| 10~4F（参数设置类） | 有 | 有 |

### 控制域 C 构造

```python
from sl427 import make_ctrl
ctrl = make_ctrl(dir_=1, func_code=0x02)  # 上行，功能码=水位
```

- `dir_`: 0=下行, 1=上行
- `func_code`: 命令与类型码（0x00~0x0F），决定数据域的类型
- 下行查询用 `dir_=0`，上行自报用 `dir_=1`

### 数据域格式（按功能码）

| 功能码 | 要素 | 字节数 | 符号 | 数组 | 数据构造方式 |
|--------|------|--------|------|------|-------------|
| 0x01 | 雨量 | 3 | 无 | 否 | BCD LE, 1位小数 |
| 0x02 | 水位 | 4 | 有 | 是 | BCD LE, 3位小数，负数额外 BIN 标记 |
| 0x0B | 土壤含水率 | 3 | 无 | 否 | BCD LE |
| 0x0D | 电压 | 2 | 无 | 否 | BCD LE, 2位小数 |
| 0x0E | 综合参数 | 1+动态 | — | — | 特殊处理 |

**BCD LE（小端）**：值 37.865 → 37865 → BCD 大端 `37865` → LE 反转 → `65 78 03 00`。

**有符号负数**：末字节高 4 位置 `0xF`。值 -12.345 → BCD LE `45 23 01 F0`。

工具函数 `int_to_bcd_bytes` + `reversed()` 可构造 BCD LE。

### Tp 编码（已有 `encode_tp`）

```python
from sl427 import encode_tp
tp = encode_tp(datetime(2026, 6, 1, 12, 0, 0), delay=0)
# 返回 7 字节：[sec, min, hour, day, month, year-2000, delay]
```

### C0 自报数据域格式（已有 `build_self_report_c0`，新方法以此为模板）

```
要素数据(D) + alarm(2B BIN LE) + state(2B BIN LE) + Tp(7B)
```

81/82/84 的自报数据域结构与 C0 **完全相同**，仅 AFN 不同。

## 要读的文件

| 文件 | 读什么 |
|------|--------|
| `docs/requirements.md` | §3.2 AFN 表、§3.5 数据域、§3.7 AUX、§3.8 Tp、§3.12 编码器 |
| `sl427/constants.py` | `AFN_MAP`、`CTRL_FUNC_MAP`（看 byteLen/decimal/signed）、`make_ctrl`、`TP_LEN`、`PW_LEN` |
| `sl427/encoder.py` | `build_frame`、`build_self_report_c0`、`encode_tp`、`encode_address`——新方法以此为模板 |
| `sl427/decoder.py` | `_parse_data_field` 中 81/82/84 分支（确认数据解析期望的结构） |

## 具体要做的事

### 1. 新增 `build_self_report_81(self_report_alarm)`

自报告警 (AFN=0x81, func_code=func, data, tp)。结构同 C0。

```python
def build_self_report_81(self, func_code: int, data: bytes,
                          tp: datetime | None = None, alarm: int = 0, state: int = 0) -> bytes:
    """自报告警数据帧 (AFN=81H)。"""
    payload = bytearray(data)
    payload.extend(alarm.to_bytes(2, "little"))
    payload.extend(state.to_bytes(2, "little"))
    ctrl = make_ctrl(dir_=1, func_code=func_code)
    return self.build_frame(0x81, ctrl, bytes(payload), tp=encode_tp(tp))
```

### 2. 新增 `build_self_report_82()`（人工置数）

同上，AFN=0x82。

### 3. 新增 `build_self_report_84()`（自报电压）

AFN=0x84。数据域为 2B BCD LE 电压值 + alarm + state + Tp。

```python
def build_self_report_84(self, voltage: float, tp: datetime | None = None) -> bytes:
    from sl651.bcd import int_to_bcd_bytes
    v = int(round(voltage * 100))
    data = bytes(reversed(int_to_bcd_bytes(v, 2)))  # BCD LE
    payload = bytearray(data)
    payload.extend((0).to_bytes(2, "little"))  # alarm
    payload.extend((0).to_bytes(2, "little"))  # state
    ctrl = make_ctrl(dir_=1, func_code=0x0D)
    return self.build_frame(0x84, ctrl, bytes(payload), tp=encode_tp(tp))
```

### 4. 新增 `build_param_set_frame()`（通用参数设置帧模板）

AFN=10~4F，含 PW 和 Tp。

```python
def build_param_set_frame(self, afn: int, func_code: int, data: bytes,
                           pw: int = 0, tp: datetime | None = None) -> bytes:
    """通用参数设置帧 (AFN=10H~4FH, AUX=PW+Tp)。"""
    ctrl = make_ctrl(dir_=0, func_code=func_code)
    pw_bytes = pw.to_bytes(2, "little")
    return self.build_frame(afn, ctrl, data, tp=encode_tp(tp), pw=pw_bytes)
```

> 注：参数设置类报文（10~4F）是下行帧（中心→终端），数据域格式各异且总数约 30 个。这里只提供**通用模板**，具体 AFN 的数据域由调用方自行构造。实际项目用到哪个 AFN 再按需补。

## 验收标准

```python
from sl427 import SL427Encoder, SL427Decoder, make_ctrl, encode_address, encode_tp
from sl651.bcd import int_to_bcd_bytes
from datetime import datetime

addr = encode_address(method=1, admin_code=110108, stn_id=1284)
enc = SL427Encoder(addr)
decoder = SL427Decoder()

# 1. 自报告警 (81)
wl_data = bytes(reversed(int_to_bcd_bytes(37865, 4)))  # 水位 37.865
f = enc.build_self_report_81(
    func_code=0x02, data=wl_data,
    tp=datetime(2026, 6, 1, 12, 0), alarm=0x0020, state=0x0070
)
r = decoder.decode(f)
assert r.crc_ok and r.afn == 0x81

# 2. 人工置数 (82)
f = enc.build_self_report_82(
    func_code=0x02, data=wl_data,
    tp=datetime(2026, 6, 1, 12, 0)
)
r = decoder.decode(f)
assert r.crc_ok and r.afn == 0x82

# 3. 自报电压 (84)
f = enc.build_self_report_84(voltage=12.36, tp=datetime(2026, 6, 1, 12, 0))
r = decoder.decode(f)
assert r.crc_ok and r.afn == 0x84

# 4. 参数设置通用帧 (11H = 设置时钟)
data = bytes([0x30, 0x00, 0x0C, 0x01, 0x06, 0x26])  # 2026-06-01 12:00:30 BCD
f = enc.build_param_set_frame(afn=0x11, func_code=0x00, data=data, pw=1234)
r = decoder.decode(f)
assert r.crc_ok
assert "下行" in r.direction
```
