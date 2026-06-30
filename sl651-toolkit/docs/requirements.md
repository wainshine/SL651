# SL651-Toolkit 需求规格说明书

> 版本：v1.2.0  
> 最后更新：2026-06-30  
> 本文件为项目需求基线，后续开发、测试、审计均以此为出发点。

---

## 一、项目概述

### 1.1 定位

提供 **SL651-2014 水文监测数据通信规约** 和 **SL427-2021 水资源监测数据传输规约** 的 Python 编解码工具包，含设备模拟器。

### 1.2 协议范围

| 协议 | 全称 | 依据 |
|------|------|------|
| SL651 | 水文监测数据通信规约 SL651-2014 | 《水文监测数据通信规约（报批稿）SL/T 651-2014》 |
| SL427 | 水资源监测数据传输规约 SL/T 427-2021 | 《水资源监测数据传输规约 SL/T 427-2021》 |

### 1.3 技术栈

- Python 3.10+
- 外部依赖：`PyYAML>=6.0`（仅多站点 YAML 配置需要）
- 模拟器 MQTT 模式：需系统安装 `mqttx` CLI（EMQX 出品，独立二进制）
- 核心解码器/编码器：**零外部依赖**

### 1.4 模块结构

```
sl651-toolkit/
├── sl651/          SL651 协议核心（bcd / crc / constants / decoder / encoder）
├── sl427/          SL427 协议核心（constants / decoder / encoder）
├── simulator/      设备模拟器（base_station / generators / water_level / rain / soil / sender / engine）
├── tools/          CLI 工具（decode_cli / simulate_cli）
├── web/            Web 解码界面（Flask app.py）
├── tests/          测试脚本（test_sl651.py, 21 项）
├── examples/       示例报文（含福建规定 23 条真实报文）
├── docs/           需求与设计文档
└── audit/          审计报告
```

---

## 二、SL651 协议

### 2.1 帧结构

**HEX/BCD 编码帧（规约表11/表12）**

```
起始符(2B) | Header(11B) | STX/SYN(1B) | Body(NB) | 结束符(1B) | CRC16(2B)
```
**ASCⅡ 编码帧**：起始符为 `01 01`(SOH) 而非 `7E 7E`。

**报头（上行，表11）**

| 偏移 | 长度 | 字段 | 编码 |
|------|------|------|------|
| 0 | 2 | 帧起始符 | `7E 7E` 或 `01 01`(ASCII) |
| 2 | 1 | 中心站地址 | 1B, 范围 1~254 |
| 3 | 5 | 遥测站地址 | 5B, 方式1/方式2 |
| 8 | 2 | 密码 | 2B HEX |
| 10 | 1 | 功能码 | 1B |
| 11 | 2 | 报文标识 | bit7=方向, bit6~0+lo=正文长度 |
| 13 | 1 | 报文起始符 | `02`(STX) 或 `16`(SYN,多包) |

**下行帧（表12）**：`[遥测站址5B]` 与 `[中心站址1B]` 顺序互换。结束符依帧类型：查询/设置用 ENQ(05H)，确认用 ACK(06H)/EOT(04H)。

**正文结构（上行定时/加报/小时报）**

| 偏移 | 长度 | 字段 | 编码 |
|------|------|------|------|
| 0 | 2 | 流水号 | 2B |
| 2 | 6 | 发报时间 | BCD YYMMDDHHmmSS |
| 8 | 2 | F1F1 | 站码标识符 |
| 10 | 5 | 站码 | 同报头遥测站址 |
| 15 | 1 | 测站类别 | 附录A分类码 |
| 16 | 2 | F0F0 | 观测时间标识符 |
| 18 | 5 | 观测时间 | BCD YYMMDDHHmm |
| 23+ | — | 要素数据 | 引导符(1B)+定义符(1B)+数据(NB) |

### 2.2 功能码（实现范围）

| 功能码 | 报文类型 | 方向 | 结束符 | 解码 | 编码 | 说明 |
|--------|----------|------|--------|------|------|------|
| `2F` | 链路维持报 | 上行 | ETX | ✅ | ✅ `build_link_maintain_frame` | 仅流水号+发报时间 |
| `30` | 测试报 | 上行 | ETX | ✅ | — | 设备检修测试 |
| `31` | 均匀报 | 上行 | ETX | ✅ | — | 等间隔 F4(雨量)/F5(水位) 数组 |
| `32` | 定时报 | 上行 | ETX | ✅ | ✅ `build_timing_frame` | 定时上报水文要素 |
| `33` | 加报报 | 上行 | ETX | ✅ | ✅ `build_alarm_frame` | 阈值触发或变化报警 |
| `34` | 小时报 | 上行 | ETX | ✅ | ✅ `build_hourly_frame` | 每小时 12 组 5min 间隔水位 |
| `35` | 人工置数报 | 上行 | ETX | ✅ | — | 人工录入数据 |
| `37` | 查询实时数据 | 下行 | ENQ | — | ✅ `build_query_frame` | 查询要素 |
| `40` | 修改基本配置 | 下行 | ENQ | — | ✅ `build_set_param_frame` | 参数设置 |
| `41` | 读取基本配置 | 下行 | ENQ | — | — | 查询响应 |
| `48` | 恢复出厂设置 | 下行 | ENQ | — | ✅ `build_reset_frame` | 恢复出厂 |
| `49` | 修改密码 | 下行 | ENQ | — | — | 修改终端密码 |
| `4A` | 设置时钟 | 下行 | ENQ | — | ✅ `build_clock_sync_frame` | 时钟校准 |

### 2.3 要素编码

**定义符机制（规约表26）**

每个要素前有 2 字节标识符：**引导符(1B)** + **定义符(1B)**。

定义符编码：高 5 位 = 数据字节数（0~31），低 3 位 = 小数位数（0~7）。

```python
def parse_def_byte(b: int) -> tuple[int, int]:
    return (b >> 3) & 0x1F, b & 0x07
```

**要素标识符表（规约附录C）** — 101 项已全部收录。支持 HEX/BCD 引导符表 `SL651_ELEMENTS` 和 ASCⅡ 标识符表 `SL651_ASCII_ELEMENTS`（161 项）。

**负数 BCD 编码（规约 6.6.3.3a）**：首字节 `0xFF` 表示负数。

**状态位解码（规约表58）**：`45H` 要素为 12-bit 压缩位掩码（交流电/蓄电池/水位/流量/水质/仪表/箱门/存储器/IC卡/水泵/剩余水量）。

### 2.4 校验算法

- **算法**: CRC-16/MODBUS (多项式反转 `0xA001`, 初值 `0xFFFF`)，覆盖 7E7E 到结束符（含）
- **字节序**: 大端
- **验证向量**: `crc16(b"123456789") == 0x4B37`

### 2.5 解码器设计

**输入**: 十六进制字符串或 bytes。自动识别 `7E7E`(HEX/BCD) 或 `0101`(ASCII) 起始。

**错误处理**:
- 报文为空 / 非HEX字符 / 奇数长度 / 非7E7E或0101开头 / 正文长度不匹配 → `DecodeError`
- 无效 BCD 数据 → 优雅降级，值显示为 `-`

**输出**: `DecodedMessage` 数据类，含报头信息、要素列表、CRC 信息、逐字节视图。

### 2.6 编码器设计

**编码器**: `SL651Encoder(center_addr, station_addr, password, station_type)`

| 方法 | 功能码 | 方向 | 结束符 | 说明 |
|------|--------|------|--------|------|
| `build_timing_frame(elements)` | 0x32 | 上行 | ETX | ✅ 定时报 |
| `build_alarm_frame(elements)` | 0x33 | 上行 | ETX | ✅ 加报报 |
| `build_hourly_frame(levels, inst, v)` | 0x34 | 上行 | ETX | ✅ 小时报（12×F5数组） |
| `build_link_maintain_frame()` | 0x2F | 上行 | ETX | ✅ 链路维持 |
| `build_ascii_frame(elements)` | 0x32 | 上行 | ETX | ✅ ASCII 编码（SOH起始） |
| `build_query_frame(guides)` | 0x37 | 下行 | ENQ | ✅ 查询要素 |
| `build_set_param_frame(params)` | 0x40 | 下行 | ENQ | ✅ 参数设置 |
| `build_clock_sync_frame(dt)` | 0x4A | 下行 | ENQ | ✅ 时钟校准 |
| `build_reset_frame()` | 0x48 | 下行 | ENQ | ✅ 恢复出厂 |
| `build_frame(func, body, dir, ascii, end_marker)` | 任意 | 任意 | 可指定 | ✅ 通用帧构造 |

**输入格式**: `elements = [(引导符, 值, 数据字节数, 小数位数), ...]`  
**负数编码**: 首字节 `0xFF` + BCD(abs(value))  
**参数校验**: `station_addr` 必须 10 位 hex → 抛 `EncodeError`；BCD 超限 → 抛 `ValueError`

---

## 三、SL427 协议

### 3.1 帧结构

```
68 L 68 | C(1B) | A(5B) | AFN(1B) | D(NB) [| PW(2B)] [| Tp(7B)] | CS(1B CRC8) | 16
```

### 3.2 AFN 功能码（实现范围）

| AFN | 报文类型 | 方向 | 解码 | 编码 | 说明 |
|-----|----------|------|------|------|------|
| `02` | 链路检测 | 上行 | ✅ | ✅ `build_heartbeat` | F0=登录/F1=退出/F2=在线保持 |
| `10` | 设置地址 (5B) | 下行 | — | ✅ `build_set_addr` | 参数设置 |
| `11` | 设置时钟 (6B BCD) | 下行 | — | ✅ `build_set_clock` | 含星期月复合字节 |
| `12` | 设置工作模式 (1B) | 下行 | — | ✅ `build_set_work_mode` | 0=自报/1=查询/2=兼容/3=调试 |
| `15` | 设置充值量 (4B BCD) | 下行 | — | ✅ `build_set_recharge` | m³ |
| `30` | IC卡功能有效 | 下行 | — | ✅ `build_set_ic_card_on` | — |
| `31` | 取消IC卡功能 | 下行 | — | ✅ `build_set_ic_card_off` | — |
| `B0` | 查询/实时值 | 上行 | ✅ | ✅ `build_query_response` | 按命令类型码解析 |
| `C0` | 自报实时数据 | 上行 | ✅ | ✅ `build_self_report_c0` | D+alarm(2B)+state(2B)+Tp(7B) |
| `81` | 自报告警 | 上行 | ✅ | ✅ `build_self_report_81` | 结构同 C0 |
| `82` | 人工置数 | 上行 | ✅ | ✅ `build_self_report_82` | — |
| `83` | 自报图片 | 上行 | ✅ | — | — |
| `84` | 自报电压 | 上行 | ✅ | ✅ `build_self_report_84` | 2B BCD 电压 |
| `61` | 查询实时图像 | 上行 | ✅ | — | — |
| `10~4F` | 参数设置(通用) | 下行 | — | ✅ `build_param_set_frame` | 通用模板 |
| `FFxx` | 用户自定义 | 任意 | ✅ | — | 双字节 AFN 扩展 |

### 3.3 控制域 C（规约表4）

| 数据位 | 定义 | 说明 |
|--------|------|------|
| D7 | DIR | 0=下行(中心→终端), 1=上行(终端→中心) |
| D6 | DIV | 0=单帧, 1=分帧(此时 C 为 2B, 增加 DIVS 拆分计数) |
| D5~D4 | FCB | 帧计数位, 防丢失重复 |
| D3~D0 | 命令与类型码 | 16 种要素类型 |

### 3.4 地址域 A（规约表7/表8）

- **方式1**: A1 = 3B BCD(行政区划码) + A2 = 2B BIN(站址, 小端, 1~60000)
- **方式2**: BYTE1 = `00H` + BYTE2~5 = 8 位 HEX 监测站编码(nibble-packed)

### 3.5 校验算法

- **算法**: CRC8, 多项式 `X7+X6+X5+X2+1` = `0xE5`, 初值 `0x00`
- **覆盖范围**: 控制域 C 到附加信息域 AUX 结束

### 3.6 编码器设计

**编码器**: `SL427Encoder(addr_bytes)`

| 方法 | 状态 | 说明 |
|------|------|------|
| `build_frame(afn, ctrl, data, tp, pw)` | ✅ | 通用帧构造，含 CRC8 |
| `build_heartbeat(hb_type)` | ✅ | 链路检测帧 (AFN=02) |
| `build_self_report_c0(func, data, tp, alarm, state)` | ✅ | 自报实时数据帧 (AFN=C0) |
| `build_self_report_81(func, data, tp, alarm, state)` | ✅ | 自报告警 (AFN=81) |
| `build_self_report_82(func, data, tp, alarm, state)` | ✅ | 人工置数 (AFN=82) |
| `build_self_report_84(voltage, tp)` | ✅ | 自报电压 (AFN=84) |
| `build_query_response(func, data)` | ✅ | 查询响应帧 (AFN=B0) |
| `build_set_addr(bytes, pw)` | ✅ | 设置地址 (AFN=10) |
| `build_set_clock(dt, pw)` | ✅ | 设置时钟 (AFN=11)，星期月复合字节 |
| `build_set_work_mode(mode, pw)` | ✅ | 设置工作模式 (AFN=12) |
| `build_set_recharge(amount, pw)` | ✅ | 设置充值量 (AFN=15) |
| `build_set_ic_card_on/off(pw)` | ✅ | IC卡功能 (AFN=30/31) |
| `build_param_set_frame(afn, func, data, pw, tp)` | ✅ | 通用参数设置帧模板 |

**辅助函数**: `make_ctrl()`, `encode_address()`, `encode_tp()`

---

## 四、设备模拟器

### 4.1 站点模型 ✅

| 站点 | 类 | 要素 | 加报触发 |
|------|-----|------|----------|
| ✅ 水位站 | `WaterLevelStation` | `0x39`(4B,3位) + `0x38`(2B,2位) | 水位变化超阈值 |
| ✅ 雨量站 | `RainStation` | `0x1F/0x1A/0x20/0x26/0x38` | 降雨状态 |
| ✅ 墒情站 | `SoilStation` | `0x10~0x13/0x38` | — |

### 4.2 发送器 ✅

| 实现 | 说明 |
|------|------|
| `MqttxSender` | 通过 `mqttx pub` CLI 子进程发送 MQTT 消息 |
| `TcpSender` | TCP socket 直连，含断线重连 |

### 4.3 引擎 ✅

`SimulatorEngine` + `StationRunner`：多站点独立线程，支持 `enable_alert`/`alert_threshold`。

### 4.4 CLI ✅

```bash
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto mqtt --broker 192.168.1.100:1883 --interval 300 --enable-alert
```

---

## 五、CLI 解码工具 ✅

```bash
python tools/decode_cli.py sl651 --hex "7E7E..."       # SL651 HEX/BCD 或 ASCII
python tools/decode_cli.py sl651 --file messages.txt   # 批量
python tools/decode_cli.py sl427 --hex "681568..."     # SL427
python tools/decode_cli.py sl651 --hex "..." -o json   # JSON 输出
```

---

## 六、Web 解码界面 ✅

```bash
python web/app.py
# 浏览器 http://localhost:5050，支持 SL651/SL427 双协议，示例加载，CRC 着色
```

---

## 七、测试覆盖

### 7.1 测试清单

| 测试 | 协议 | 覆盖点 |
|------|------|--------|
| `test_bcd` | 通用 | BCD 编解码、时间编解码 |
| `test_crc` | 通用 | CRC-16/MODBUS 验证向量 |
| `test_def_byte` | SL651 | 定义符解析 (0x23→4,3) |
| `test_decode_njnrs` | SL651 | njnrs 示例报文解码 (CRC+要素) |
| `test_decode_watertester` | SL651 | 水测家加报报解码 (含自定义要素) |
| `test_encode_decode_roundtrip` | SL651 | 编码→解码往返一致性 |
| `test_sl651_downlink_frames` | SL651 | 查询/设置/校时/复位 四类下行帧（验证结束符 ENQ） |
| `test_sl651_ascii` | SL651 | ASCII 编码帧往返（SOH 起始） |
| `test_negative_bcd` | SL651 | 负数 BCD 0xFF前缀往返 |
| `test_invalid_bcd_graceful` | SL651 | 无效 BCD 降级不崩溃 |
| `test_crc8` | SL427 | CRC8 验证 |
| `test_sl427_decode` | SL427 | njnrs 示例报文解码 |
| `test_sl427_encoder_roundtrip` | SL427 | heartbeat + C0 往返 |
| `test_sl427_address_encoding` | SL427 | 方式1/方式2 地址编码 + 异常输入 |
| `test_sl427_tp_encoding` | SL427 | 7B 时间标签各字段 |
| `test_sl427_c0_signed_value` | SL427 | 有符号水位负数往返 |
| `test_sl427_invalid_l` | SL427 | 畸形 L 拒绝 |
| `test_sl427_downlink` | SL427 | 下行帧解码 |
| `test_sl427_param_settings` | SL427 | 设置地址/时钟/充值/IC卡 往返 |
| `test_fujian_messages` | SL651 | **23 条福建规定真实报文 CRC 验证** |

**总计: 21 项**，全部通过。

### 7.2 福建规定报文测试 ⭐

来源：《福建省水文监测数据接入规定 V1.0》（福建省水文水资源勘测中心，2023-01）。

```bash
# 批量验证
python tools/decode_cli.py sl651 --file examples/fujian_messages.txt

# 覆盖 23 条报文，14 种功能码：
# 31(均匀报) / 32(定时报) / 33(加报报) / 34(小时报) / 35(人工置数)
# 36 / 37(查询) / 38 / 3A / 40(修改配置) / 41(读取配置)
# 42 / 43 / 45 / 46 / 47 / 48(恢复出厂) / 49(修改密码) / 4A(设置时钟) / 50 / 51
```

---

## 八、待实现 Roadmap

### ✅ P1 — 已完成

| 任务 | 状态 |
|------|------|
| SL651 编码器补全（2F/33/34） | ✅ |
| SL427 编码器补全（81/82/84） | ✅ |
| SL651 FUNC_MAP 补全（0x35 等） | ✅ |

### ✅ P2 — 已完成

| 任务 | 状态 |
|------|------|
| SL427 参数设置/查询（10H~4FH 通用模板 + 6 个便捷方法） | ✅ |
| 模拟器加报机制（雨量站/水位站触发） | ✅ |
| ASCII 编码帧支持（SOH 起始，解码+编码） | ✅ |
| 福建规定 23 条真实报文验证 | ✅ |

### ✅ P3 — 已完成

| 任务 | 状态 |
|------|------|
| SL651 下行帧编码（查询/设置/校时/复位，规约功能码+ENQ结束符） | ✅ |
| Web UI（Flask 单文件解码界面） | ✅ |

### ⬜ 远期（P4）

| 任务 | 说明 |
|------|------|
| 多包 (SYN/ETB) 拼接重组 | 当前可解码单帧多包，不支持拼接 |
| 模拟器集成测试 | 端到端 MQTT broker 联调 |
| SL427 参数设置全量 AFN | 当前通用模板 + 6 个便捷方法，剩余 ~20 个变长 AFN 未实现具体数据域 |
