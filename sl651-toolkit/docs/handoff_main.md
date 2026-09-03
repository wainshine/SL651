# SL651-Toolkit 交接文档

> 最后更新：2026-09-03  
> 版本：v1.2.6  
> 接手前必读：`docs/project.md` + 项目 `README.md` + 本文档

---

## 零、文档分工与更新原则

| 文档 | 侧重 | 更新原则 |
|------|------|----------|
| `README.md` | 用户入口：快速上手、目录结构、CLI 用法、API 示例、版本历史 | 每次发版时更新版本号和变更摘要 |
| `docs/project.md` | 项目基线：协议规格、功能码矩阵、要素编码、测试清单、Roadmap | 需求变更 / 功能补全 / 测试增减时同步更新 |
| `docs/handoff_main.md` | 交接总览：当前状态、核心能力、TODO、设计决策、常见问题 | 版本迭代后更新状态、闭环 TODO、补充决策记录 |

---

## 一、项目当前状态

### 1.1 测试状态

```
44 项测试全部通过（另有盲区测试 10 项）
福建 23 条真实报文 CRC 全通过
北京 25 条真实报文 CRC 全通过
```

### 1.2 版本号

`sl651/__init__.py:__version__ = "1.2.6"`

### 1.3 完成的审计轮次

v1.1~v2.1，共 11 轮，全部缺陷已闭环。v1.10/v2.0 综合参数/小时报F4/统计雨量等缺陷在 v1.2.4 全部修复；v2.1 异常契约/线程安全/编码器校验等缺陷在 v1.2.5 全部修复。

### 1.4 v1.2.6 自审计修复（主会话 4 代，2026-09-03）

- 文档一致性修正 8 处（测试计数滞后、行号漂移、参数名不符）
- B1: SL427 `_fmt_time_427` 非法 BCD 半字节静默归零 → 统一"无效时间"占位
- B2: SL651 F3 图片要素改字节摘要显示（不再数值化出天文数字）
- B3: ASCII 编码器拒绝保留引导符 ST/TT（抛 EncodeError）
- 测试 41 → 44 项，全部通过

---

## 二、核心能力清单

### 2.1 SL651 解码

| 功能 | 状态 | 关键文件 |
|------|------|----------|
| HEX/BCD 帧解码 | ✅ | `sl651/decoder.py` |
| ASCII 帧解码 (SOH起始) | ✅ | `sl651/decoder.py:_parse_ascii_elements` |
| 定义符动态解析 | ✅ | `sl651/constants.py:parse_def_byte` |
| 101 项要素标识符 | ✅ | `sl651/constants.py:SL651_ELEMENTS` |
| 102 项 ASCII 标识符 | ✅ | `sl651/constants.py:SL651_ASCII_ELEMENTS` |
| FF 子标识符（含北京/水测家） | ✅ | `sl651/constants.py:SL651_CUSTOM` |
| 12-bit 状态位解码 | ✅ | `sl651/decoder.py:_parse_status` |
| F4/F5 均匀报数组 | ✅ | `sl651/decoder.py:_parse_f4_array/_parse_f5_array` |
| 负数 BCD (0xFF前缀) | ✅ | `sl651/encoder.py:_encode_bcd` |
| CRC-16/MODBUS | ✅ | `sl651/crc.py` |

### 2.2 SL651 编码

| 方法 | 功能码 | 方向 | 结束符 |
|------|--------|------|--------|
| `build_timing_frame` | 0x32 | 上行 | ETX |
| `build_alarm_frame` | 0x33 | 上行 | ETX |
| `build_hourly_frame` | 0x34 | 上行 | ETX |
| `build_link_maintain_frame` | 0x2F | 上行 | ETX |
| `build_ascii_frame` | 0x32 | 上行 | ETX |
| `build_query_frame` | 0x37 | 下行 | ENQ |
| `build_set_param_frame` | 0x40 | 下行 | ENQ |
| `build_clock_sync_frame` | 0x4A | 下行 | ENQ |
| `build_reset_frame` | 0x48 | 下行 | ENQ |

### 2.3 SL427 解码

| 功能 | 状态 | 关键文件 |
|------|------|----------|
| 68H 帧解析 + CRC8 | ✅ | `sl427/decoder.py` |
| AFN 分派 (02/C0/B0/61/81/82/83/84/FF) | ✅ | `sl427/decoder.py:_parse_data_field` |
| 地址域方式1/方式2 | ✅ | `sl427/decoder.py:_format_addr` |
| Tp 时间标签 (7B) | ✅ | `sl427/decoder.py:_fmt_time_427` |
| 告警状态 (14 bit) | ✅ | `sl427/decoder.py:_parse_alarm` |
| 终端状态 (7 bit) | ✅ | `sl427/decoder.py:_parse_terminal` |
| 综合参数 (0x0E) | ✅ | `sl427/decoder.py:_parse_comprehensive` |
| 有符号 BCD LE | ✅ | `sl427/decoder.py:_parse_signed_bcd` |

### 2.4 SL427 编码

| 方法 | AFN | 方向 |
|------|-----|------|
| `build_heartbeat` | 0x02 | 上行 |
| `build_self_report_c0` | 0xC0 | 上行 |
| `build_self_report_81` | 0x81 | 上行 |
| `build_self_report_82` | 0x82 | 上行 |
| `build_self_report_84` | 0x84 | 上行 |
| `build_query_response` | 0xB0 | 上行 |
| `build_set_addr` | 0x10 | 下行 |
| `build_set_clock` | 0x11 | 下行 |
| `build_set_work_mode` | 0x12 | 下行 |
| `build_set_recharge` | 0x15 | 下行 |
| `build_set_ic_card_on/off` | 0x30/0x31 | 下行 |
| `build_param_set_frame` | 10~4F | 下行 |

### 2.5 模拟器

| 功能 | 状态 |
|------|------|
| 水位站 (N(7,3)精度) | ✅ |
| 雨量站 (含加报) | ✅ |
| 墒情站 | ✅ |
| MQTT 发送 (mqttx CLI) | ✅ |
| TCP 发送 (含重连) | ✅ |
| 加报机制 (雨量/水位触发) | ✅ |
| YAML 多站点 | ✅ |

### 2.6 CLI & Web

| 功能 | 状态 |
|------|------|
| `decode_cli sl651 --hex/text/json` | ✅ |
| `decode_cli sl427 --hex/text/json` | ✅ |
| `simulate_cli --type/--proto/--broker/--config` | ✅ |
| `web/app.py` Flask 解码界面 (端口 5050) | ✅ |

---

## 三、待处理 (TODO)

### 3.1 立即 (P1)

| 任务 | 位置 | 说明 |
|------|------|------|
| 模拟器引擎集成测试 | `tests/` | 当前仅有冒烟测试 (`test_simulator_engine_smoke`)，缺少端到端 MQTT broker 联调 |
| round1 盲区测试纳入 CI | `tests/test_round1_blindspots.py` | 10 项盲区测试已全部修复通过，建议纳入例行运行 |

### 3.2 远期 (P2)

| 任务 | 说明 |
|------|------|
| SL427 参数设置全量 AFN (~30个变长格式) | 当前仅有通用模板 + 6 个便捷方法 |
| SL427 ASCII 编码帧 | SL427 文本帧解码 |
| 多包 (SYN/ETB) 拼接重组 | 当前已处理 SYN 单帧偏移，不支持跨帧拼接 |
| 45H 状态位 32 位全量 | 当前缩减为 12 位 |
| 0x26 累计雨量独立计数器 | 模拟器雨量站当前用日累计近似 |

### 3.3 设计保留项（不修）

| 项 | 位置 | 原因 |
|----|------|------|
| `AFN_NO_AUX` / `AFN_TP_ONLY` / `AFN_PW_TP` | `sl427/constants.py:135` | 文档用途，编解码器在调用处硬编码 AUX 逻辑 |
| A1 行政区划码大端 BCD | `sl427/encoder.py:51` | 待实物验证 |

---

## 四、怎样快速接手

### 4.1 必读文件（按顺序）

1. **`docs/project.md`** — 协议需求、功能码矩阵、测试清单、Roadmap
2. **`README.md`** — 目录结构、CLI 用法、版本历史
3. **`sl651/constants.py`** — 要素表、FUNC_MAP、STATUS_BITS
4. **`sl427/constants.py`** — AFN_MAP、CTRL_FUNC_MAP、ALARM_BITS

### 4.2 了解编解码器

```bash
# 解码一条报文看看输出格式
python tools/decode_cli.py sl651 --hex "7E7E2500418D233700..."

# 跑全部测试
python tests/test_sl651.py

# 跑福建/北京真实报文
python tools/decode_cli.py sl651 --file examples/fujian_messages.txt
python tools/decode_cli.py sl651 --file examples/beijing_messages.txt
```

### 4.3 编码器使用

```python
from sl651 import SL651Encoder
from datetime import datetime

enc = SL651Encoder(center_addr=0x01, station_addr="1234567890", password=0, station_type=0x48)
frame = enc.build_timing_frame([(0x39, 12.345, 4, 3)], obs_time=datetime.now())
# frame.hex() 就是完整 SL651 帧
```

### 4.4 SL427 编码器使用

```python
from sl427 import SL427Encoder, encode_address, make_ctrl

addr = encode_address(method=1, admin_code=110108, stn_id=1284)
enc = SL427Encoder(addr)
frame = enc.build_heartbeat()  # 链路检测
frame = enc.build_self_report_c0(func_code=0x02, data=wl_bytes)
frame = enc.build_set_clock(datetime.now())  # 下行校时
```

---

## 五、关键设计决策记录

| 决策 | 说明 |
|------|------|
| **CRC16 用 MODBUS 而非 CCITT** | 多项式 `0xA001`，与 njnrs 和真实报文 CRC 一致 |
| **SL427 CS 用 CRC8 而非算术和** | 多项式 `0xE5`，与 njnrs 示例 CRC=0xAD 验证通过 |
| **负数 BCD 用 0xFF 前缀** | 编码器 `0xFF` 前缀方案，解码器剥离后负号运算 |
| **SL427 Tp 第7字节 = 传输延时时长** | 规约 6.3.3.8 确认（非 IEC 星期） |
| **SL427 地址域 A2 用 BIN 小端** | 规约表7 确认（非 BCD） |
| **CLI 输出脱敏** | 中心站址只显示前 2 位，遥测站址只显示前 4 位，密码不显示 |
| **下行帧结束符选 ENQ** | 规约表12，查询/设置/校时/复位均用 ENQ(05H) |
| **模拟器 MQTT 不用 paho-mqtt** | 改用 `mqttx` CLI 子进程，`requirements.txt` 无 MQTT 依赖 |

---

## 六、测试文件说明

| 文件 | 内容 |
|------|------|
| `tests/test_sl651.py` | 44 项测试：BCD/CRC/定义符/编解码往返/福建23条/北京25条/模拟器冒烟/编码器校验/Web API 等 |
| `examples/sample_messages.txt` | njnrs + 水测家示例 |
| `examples/fujian_messages.txt` | 福建规定 23 条 (14种功能码) |
| `examples/beijing_messages.txt` | 北京水务平台 25 条 (8测站, 3类报文) |

---

## 七、依赖

```
Python 3.10+
PyYAML>=6.0     # 仅 simulate_cli --config YAML 模式需要
flask            # 仅 web/app.py 需要
# 模拟器 MQTT 模式需系统安装 mqttx CLI 二进制
```

---

## 八、常见问题

**Q: 为什么 F5 水位值 4.28m 而官方平台显示 234.28m？**

A: SL651 传输的是**相对水位**，平台展示的是**绝对水位** = 相对水位 + 水位基值 (230m)。不是 bug。

**Q: CRC16 算法验证？**

A: `crc16(b"123456789") == 0x4B37`（CRC-16/MODBUS 验证向量，通过）

**Q: SL427 CRC8 多项式确认？**

A: `X7+X6+X5+X2+1 = 0xE5`，初值 0x00，与 njnrs 示例 CRC=0xAD 双向印证。
