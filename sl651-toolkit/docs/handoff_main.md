# SL651-Toolkit 交接文档

> 最后更新：2026-09-14  
> 版本：v1.3.1  
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
python tests/run_all.py  → 8/8 套件通过
  主套件 59 项 / 盲区 10 项 / 模拟器集成 5 组 / 解码器变异 3 组
  / SL427 参数 AFN 13 组 / SL427 查询 AFN 21 组 / SL427 控制 AFN 10 组 / SL651 多包重组 6 组
福建 23 条真实报文 CRC + 要素级基线全通过
北京 25 条真实报文 CRC + 要素级基线全通过
```

### 1.2 版本号

`sl651/__init__.py:__version__ = "1.3.1"`

### 1.3 完成的审计轮次

v1.1~v2.3，共 13 轮。v1.2.4 修复 v1.10/v2.0 综合参数/小时报F4/统计雨量等；v1.2.5 修复 v2.1 异常契约/线程安全/编码器校验；v1.2.6 修复 3 项自审计缺陷；v1.2.7 修复 v2.2 的 1C+5M+7L 全部缺陷；v1.2.8 工程化 + 测试深度 + SL427 参数 AFN；v1.3.0 SL427 全 AFN + SL651 编码器补全 + 多包重组；v1.3.1 修复 v2.3 的 4M+6L。

### 1.4 v1.3.1 审计 v2.3 修复（主会话 6 代，2026-09-14）

- M-1: `sl651/constants.py` `FUNC_MAP` 0x38~0x51 名称按规约正文重写，补齐 0x39/0x44/0x4B~0x4F（原 0x44「未知」、0x45~0x51 错误）
- M-2: `sl427/decoder.py` 查询/控制响应对规约合法 `0xAA`/`0xFF` 缺测填充降级 `-`，不再抛 `DecodeError`
- M-3: `sl651/decoder.py` 人工置数报 `F2` 契约统一（F2 后为原编码载荷，无定义符），福建 0x35 恢复 1 要素
- M-4: `sl427/encoder.py` `build_set_addr`（固定 5B）/`build_set_channel`（按类型码校验）补长度校验
- L-1~L-6: 5CH 名称 / ASCII 多包方向位 / 死键 `DRxnn` / 0x26 量程注释 / 福建示例注释 / handoff_test 计数
- 测试: 主套件 57 → 59 项；辅助套件补 0xAA 填充容错、地址长度校验、ASCII 方向位

### 1.5 v1.3.0 SL427 全 AFN 与 SL651 编码器补全（主会话 5 代，2026-09-14）

- 功能: SL427 查询类 AFN 50H~65H 查询帧 + 响应解析（50/51/52/53/54/55/56/57/58/59/5A/5D/5E/5F/60/62/63/64/65H）
- 功能: SL427 控制/配置 AFN 90H~96H、A0H~A2H（复位/清空/启停泵/切换/改密/实时种类/自报种类/主备信道）
- 功能: SL427 `AFN_MAP` 扩至 61 项；5CH 历史日记录查询帧（响应字段规约未定义）
- 功能: SL651 多包 SYN/ETB 流式重组 `feed()`（表22，支持乱序/增量/垃圾字节）
- 功能: SL651 编码器补 0x30/0x35/41H/42H/43H/44H/45H/46H/47H/49H/50H/51H
- 修复: 模拟器 0x26 不归零累计
- 测试: 主套件 57 项 + 7 个辅助套件（`run_all.py` 8/8）

### 1.6 v1.2.8 工程化与功能扩展（主会话 5 代，2026-09-14）

- 工程化: `tests/run_all.py` 统一入口 + `.github/workflows/ci.yml`
- 测试: 模拟器端到端集成（真实 TCP）、解码器变异测试（各 600 次）
- 功能: SL427 参数 AFN 16H~20H 共 11 个便捷方法
- 规约核查: 关闭 SL427 ASCII 帧 / 45H 32 位两个伪需求
- 测试: 主套件 53 项 + 4 个辅助套件（`run_all.py` 5/5）

### 1.7 v1.2.7 审计 v2.2 修复（主会话 5 代，2026-09-14）

- C-1: 0x31 均匀报「标识符组一次 + 多组重复数据」解析（原静默丢失 11/12 组）
- M-1: F4/F5 固定 12B/24B，定义符失配写 `warnings` 并继续，消除截断 + 垃圾要素
- M-2: SL427 84H 按规范表B.98 修正为「仅 2B 电压、无 Tp」，移除 `tp` 参数与解码分支
- M-3: BCD 超限统一 `EncodeError`；M-5: 正文 ≤4095 校验
- M-4: 真实报文要素级基线（要素数 + 首末值），修复「CRC 通过 ≠ 要素正确」根因
- L-1~L-6 及文档 D-1~D-11 全部处理；测试 44 → 53 项
- 收尾：SL427 `DecodedMessage.warnings`（短数据域降级可见）；0x31 ASCII 均匀报时间步长码 `DRxnn` 识别 + 多值数组

### 1.8 v1.2.6 自审计修复（主会话 4 代，2026-09-03）

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
| 101 项 ASCII 标识符 | ✅ | `sl651/constants.py:SL651_ASCII_ELEMENTS`（时间步长码动态识别） |
| FF 子标识符（含北京/水测家） | ✅ | `sl651/constants.py:SL651_CUSTOM` |
| 12-bit 状态位解码 | ✅ | `sl651/decoder.py:_parse_status` |
| F4/F5 均匀报数组 | ✅ | `sl651/decoder.py:_parse_f4_array/_parse_f5_array` |
| 负数 BCD (0xFF前缀) | ✅ | `sl651/encoder.py:_encode_bcd` |
| CRC-16/MODBUS | ✅ | `sl651/crc.py` |
| 流式解析 + 多包重组 | ✅ | `sl651/decoder.py:feed` |

### 2.2 SL651 编码

| 方法 | 功能码 | 方向 | 结束符 |
|------|--------|------|--------|
| `build_timing_frame` | 0x32 | 上行 | ETX |
| `build_test_frame` | 0x30 | 上行 | ETX |
| `build_manual_frame` | 0x35 | 上行 | ETX |
| `build_read_config_frame` | 0x41/0x43 | 下行 | ENQ |
| `build_init_solid_storage` | 0x47 | 下行 | ENQ |
| `build_change_password_frame` | 0x49 | 下行 | ENQ |
| `build_alarm_frame` | 0x33 | 上行 | ETX |
| `build_hourly_frame` | 0x34 | 上行 | ETX |
| `build_link_maintain_frame` | 0x2F | 上行 | ETX |
| `build_ascii_frame` | 0x32 | 上行 | ETX |
| `build_query_frame` | 0x37 | 下行 | ENQ |
| `build_query_pump_data/software_version/status_alarm/event_record/clock` | 44/45/46/50/51 | 下行 | ENQ |
| `build_query_body` | 3A | 下行 | ENQ |
| `build_set_param_frame` | 0x40 | 下行 | ENQ |
| `build_clock_sync_frame` | 0x4A | 下行 | ENQ |
| `build_reset_frame` | 0x48 | 下行 | ENQ |
| `build_frame` | 任意 | 任意 | 可指定 |

### 2.3 SL427 解码

| 功能 | 状态 | 关键文件 |
|------|------|----------|
| 68H 帧解析 + CRC8 | ✅ | `sl427/decoder.py` |
| AFN 分派 (02/C0/B0/61/81/82/83/84/FF + 50~65/90~96/A0~A2 响应) | ✅ | `sl427/decoder.py:_parse_data_field` |
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
| `build_set_recharge_alarm` | 0x16 | 下行 |
| `build_set_level_limits` | 0x17 | 下行 |
| `build_set_pressure_limits` | 0x18 | 下行 |
| `build_set_water_quality` | 0x19/0x1A | 下行 |
| `build_set_water_amount` | 0x1B | 下行 |
| `build_set_relay_code_len` | 0x1C | 下行 |
| `build_set_relay_addr` | 0x1D | 下行 |
| `build_set_relay_auto_switch` | 0x1E | 下行 |
| `build_set_flow_limits` | 0x1F | 下行 |
| `build_set_report_threshold` | 0x20 | 下行 |
| `build_set_ic_card_on/off` | 0x30/0x31 | 下行 |
| `build_query_*`（17 个，含 5CH 历史日记录） | 0x50~0x65 | 下行 |
| `build_reset/clear_history/start_pump/stop_pump/switch_comm/switch_relay_work/change_password` | 0x90~0x96 | 下行 |
| `build_set_realtime_kinds/report_kinds/channel` | 0xA0~0xA2 | 下行 |
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

| 任务 | 位置 | 状态 |
|------|------|------|
| 统一测试入口 `tests/run_all.py` | `tests/run_all.py` | ✅ v1.2.8 已提供 |
| round1 盲区测试纳入 CI | `.github/workflows/ci.yml` | ✅ v1.2.8 已纳入（Python 3.10/3.11/3.12） |
| 模拟器引擎集成测试 | `tests/test_simulator_integration.py` | ✅ v1.2.8 已补（FakeSender/真实 TCP 全链路） |

### 3.2 远期 (P2)

| 任务 | 说明 |
|------|------|
| SL427 参数/查询/控制 AFN | ✅ 参数 10H~20H、30H~31H（v1.2.8）；查询 50H~65H、控制/配置 90H~96H、A0H~A2H（v1.3.0） |
| SL427 查询响应全量解析 | ✅ 已解析 50/51/52/53/54/55/56/57/58/59/5A/5D/5E/5F/60/62/63/64/65H（v1.3.0）；仅 5CH(历史日记录)以字节摘要显示（规约未定义） |
| SL427 下行参数/查询帧解码 | 下行帧仅显示「下行报文」摘要，未回显命令数据域 |
| ~~多包 (SYN/ETB) 拼接重组~~ | ✅ v1.3.0 已实现流式重组 `feed()`（表22） |
| ~~45H 状态位 32 位全量~~ | 不存在：规约表58 仅定义 BIT0~11，BIT12~31 保留；当前 12 位与规约一致 |
| ~~SL427 ASCII 编码帧~~ | 不存在：SL427 全文无 ASCII 编码，帧固定 68H…16H |
| ~~0x26 累计雨量独立计数器~~ | ✅ v1.3.0 已实现不归零累计（`RainGenerator.total_accum`，上限 99999.9mm 翻转） |

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
| **多包重组按「完整正文分段拼接」** | `feed()` 将各 SYN 包 SYN 后正文（含流水号）按序列号拼接为完整正文（规约 6.6.4 表注：发送端对完整正文分包），支持乱序/增量/垃圾字节 |
| **47H 标识符 97H / 49H 标识符 03H** | 依据附录 D #120「固态存储数据初始化 97H」、表 D.1 #3「密码 03H」；福建样本字节序与表65 略有出入，已按规约表实现 |
| **0x26 累计雨量为不归零累计** | `RainGenerator.total_accum`，上限 99999.9mm（N(5,1)）后翻转；日/小时累计仍按周期归零 |

---

## 六、测试文件说明

| 文件 | 内容 |
|------|------|
| `tests/run_all.py` | 统一入口：依次运行下列全部套件 |
| `tests/test_sl651.py` | 59 项测试：BCD/CRC/定义符/编解码往返/福建23条+北京25条（CRC + 要素级基线）/0x31均匀报/F5固定长度/模拟器冒烟/编码器校验/Web API/功能码名称一致性/人工置数 F2 等 |
| `tests/test_round1_blindspots.py` | 10 项盲区测试 |
| `tests/test_simulator_integration.py` | 5 组端到端集成（含 TcpSender 真实 TCP 收发、0x26 累计） |
| `tests/test_fuzz_decoders.py` | 解码器变异测试（SL651/SL427 各 600 次）+ `feed()` 流式健壮性 |
| `tests/test_sl427_param_afn.py` | SL427 参数 AFN 16H~20H 数据域布局测试 |
| `tests/test_sl427_query_afn.py` | SL427 查询类 AFN 50H~65H 查询帧 + 响应解析测试 |
| `tests/test_sl427_control_afn.py` | SL427 控制/配置 AFN 90H~96H、A0H~A2H 测试 |
| `tests/test_sl651_multipacket.py` | SL651 多包 SYN/ETB 重组测试 |
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
