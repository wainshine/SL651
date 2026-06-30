# 任务 1：SL651 编码器补全

## 职责边界

在现有 `sl651/encoder.py` 的 `SL651Encoder` 类中，新增三个便捷编码方法，并补全常量表。

**不需要做**：
- 不需要修改解码器
- 不需要修改模拟器
- 不需要改 SL427 相关代码
- 不需要读 PDF 规格文档

## 背景知识

### SL651 帧结构（已有代码实现）

```
7E7E | Header(11B) | STX(02) | 流水号(2B) | 发报时间(6B BCD) | 正文 | ETX(03) | CRC16(2B)
```

- CRC16 = MODBUS（多项式 0xA001, 初值 0xFFFF），覆盖 7E7E 到 ETX
- 现有 `build_frame()` 已完整实现帧构造，新方法只需构造 body 后调用它

### 三种报文的正文字节布局

**2F 链路维持报**：正文 = 流水号+发报时间。无 F1F1/F0F0/要素数据。

**33 加报报**：正文 = 流水号+发报时间 + F1F1+站码+类型+F0F0+观测时间+要素。**与 32 定时报完全相同**，仅功能码不同。

**34 小时报**：正文 = 流水号+发报时间 + F1F1+站码+类型+F0F0+观测时间 + F5数组(12×2B HEX) + 瞬时水位(39) + 电池电压(38)。

- F5 数组：12 个 2 字节 HEX 值，每值 = 水位毫米数。`0x0000` = 0.00m，`0xFFFF` = 无效。
- F5 引导符 + 定义符 `0xC0` → `parse_def_byte(0xC0)` = len=24, dec=2

## 要读的文件

| 文件 | 读什么 |
|------|--------|
| `docs/requirements.md` | §2.2 功能码表（看 2F/33/34 的正文特征）、§2.7 编码器设计 |
| `sl651/constants.py` | `FUNC_MAP`（看现有格式，确认是否缺 0x35）、帧偏移常量、`STX`/`ETX`/`START_BYTE` |
| `sl651/encoder.py` | 现有 `build_frame()` 和 `build_timing_body()` 的完整实现（这是模板！） |
| `sl651/decoder.py` | `decode()` 方法中如何判断 2F（无 F1F1/F0F0）和 34（含 F5 数组） |

## 具体要做的事

### 1. 补全 FUNC_MAP（`constants.py`）

在现有 6 个条目后添加：
```python
0x35: "人工置数报",
```

### 2. 新增 `build_link_maintain_body()` 和 `build_link_maintain_frame()`（`encoder.py`）

```python
def build_link_maintain_body(self) -> bytes:
    """链路维持报正文：仅流水号+发报时间，无 F1F1/F0F0。"""
    # 正文为空，流水号+发报时间由 build_frame 自动在前面加上
    return b""

def build_link_maintain_frame(self) -> bytes:
    """链路维持报 (0x2F)。"""
    return self.build_frame(0x2F, self.build_link_maintain_body())
```

### 3. 新增 `build_alarm_body()` 和 `build_alarm_frame()`（`encoder.py`）

```python
def build_alarm_body(self, elements, obs_time=None):
    """加报报正文：与定时报相同（F1F1+站码+类型+F0F0+观测时间+要素）。"""
    return self.build_timing_body(elements, obs_time)

def build_alarm_frame(self, elements, obs_time=None):
    """加报报 (0x33)。"""
    return self.build_frame(0x33, self.build_alarm_body(elements, obs_time))
```

### 4. 新增 `build_hourly_body()` 和 `build_hourly_frame()`（`encoder.py`）

正文结构：F1F1+站码+类型+F0F0+观测时间 + **F5数组(24B)** + 瞬时水位 + 电池电压。

```python
def build_hourly_body(self, water_levels, inst_level, voltage, obs_time=None):
    """
    water_levels: 12 个水位值列表，单位米。如 [0, 0, 0.05, ...]
    inst_level: 瞬时水位，米
    voltage: 电池电压，伏
    """
    if obs_time is None:
        obs_time = datetime.now()
    ot = datetime_to_bcd(obs_time)[:5]
    
    body = bytearray()
    body.append(0xF1); body.append(0xF1)
    body.extend(self.station_addr_bytes)
    body.append(self.station_type)
    body.append(0xF0); body.append(0xF0)
    body.extend(ot)
    
    # F5 数组：引导符(0xF5) + 定义符(0xC0=24B,2位小数) + 12×2B HEX
    body.append(0xF5)
    body.append(_make_def_byte(24, 2))
    for wl in water_levels:
        if wl is None:
            body.extend(b'\xFF\xFF')       # 无效值标记
        else:
            val = int(round(wl * 100))     # 米→厘米→int
            body.extend(val.to_bytes(2, 'big'))
    
    # 瞬时水位
    body.append(0x39)
    body.append(_make_def_byte(4, 3))
    body.extend(_encode_bcd(inst_level, 4, 3))
    
    # 电池电压
    body.append(0x38)
    body.append(_make_def_byte(2, 2))
    body.extend(_encode_bcd(voltage, 2, 2))
    
    return bytes(body)

def build_hourly_frame(self, water_levels, inst_level, voltage, obs_time=None):
    """小时报 (0x34)。"""
    return self.build_frame(0x34, self.build_hourly_body(water_levels, inst_level, voltage, obs_time))
```

注意：`_make_def_byte`、`_encode_bcd`、`datetime_to_bcd` 已在 `encoder.py` 顶部或 `bcd.py` 中定义，直接引用即可。

## 验收标准

```python
from sl651.encoder import SL651Encoder
from sl651.decoder import SL651Decoder
from datetime import datetime

enc = SL651Encoder(center_addr=0x01, station_addr="00418D2337", password=0, station_type=0x48)
decoder = SL651Decoder()

# 1. 链路维持报 (2F)
f = enc.build_link_maintain_frame()
r = decoder.decode(f)
assert r.crc_ok
assert r.function_code == 0x2F
assert r.function_name == "链路维持报"

# 2. 加报报 (33)
f = enc.build_alarm_frame([(0x39, 12.345, 4, 3)], obs_time=datetime(2025,6,1,12,0))
r = decoder.decode(f)
assert r.crc_ok and r.function_code == 0x33

# 3. 小时报 (34)
f = enc.build_hourly_frame(
    water_levels=[0]*12,
    inst_level=12.345,
    voltage=12.6,
    obs_time=datetime(2025,6,1,12,0)
)
r = decoder.decode(f)
assert r.crc_ok and r.function_code == 0x34
# 应该有 F5 12组水位 + 39 瞬时水位 + 38 电压 = 14 要素
assert len(r.elements) >= 14
```
