# SL651-Toolkit 项目规格说明书

> 版本：v1.3.2  
> 最后更新：2026-09-14  
> 原名 `requirements.md`，v1.2.3 起更名为 `project.md`。历史审计报告（v1.4~v1.9）中的 `requirements.md` 引用即指本文档。

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
├── tests/          测试脚本（run_all.py 统一入口；test_sl651.py 61 项 + 盲区/模拟器集成/变异/SL427 参数·查询·控制/SL651 多包 7 个辅助套件）
├── examples/       示例报文（福建规定 23 条 / 北京水务 25 条真实报文）
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
**ASCⅡ 编码帧**：起始符为单 `01`(SOH) 而非 `7E 7E`；兼容旧双 `01 01` 方言。

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
| `30` | 测试报 | 上行 | ETX | ✅ | ✅ `build_test_frame` | 设备检修测试 |
| `31` | 均匀报 | 上行 | ETX | ✅ | — | 等间隔：标识符组仅一次 + 多组重复数据（§6.6.4.4 表30） |
| `32` | 定时报 | 上行 | ETX | ✅ | ✅ `build_timing_frame` | 定时上报水文要素 |
| `33` | 加报报 | 上行 | ETX | ✅ | ✅ `build_alarm_frame` | 阈值触发或变化报警 |
| `34` | 小时报 | 上行 | ETX | ✅ | ✅ `build_hourly_frame` | 每小时 12 组 5min 间隔水位 |
| `35` | 人工置数报 | 上行 | ETX | ✅ | ✅ `build_manual_frame` | F2 标识符 + 原编码数据 |
| `36` | 图片报 | 上行 | ETX | ✅ | — | 图片信息（F3 标识符） |
| `37` | 查询实时数据 | 下行 | ENQ | — | ✅ `build_query_frame` | 查询所有实时数据（表42） |
| `38` | 查询时段数据 | 下行 | ENQ | — | — | 中心站查询遥测站指定要素时段数据 |
| `39` | 查询人工置数 | 下行 | ENQ | — | — | 中心站查询遥测站人工置数 |
| `3A` | 查询指定要素 | 下行 | ENQ | — | ✅ `build_query_body` | 正文含要素引导符列表 |
| `40` | 修改基本配置 | 下行 | ENQ | — | ✅ `build_set_param_frame` | 参数设置 |
| `41` | 读取基本配置 | 下行 | ENQ | — | ✅ `build_read_config_frame` | 参数标识符列表（附录D） |
| `42` | 修改运行参数 | 下行 | ENQ | — | ✅ `build_set_param_frame(fc=0x42)` | 同 40H 正文 |
| `43` | 读取运行参数 | 下行 | ENQ | — | ✅ `build_read_config_frame(fc=0x43)` | 参数标识符列表（附录D） |
| `44` | 查询水泵电机数据 | 下行 | ENQ | — | ✅ `build_query_pump_data` | 空正文 |
| `45` | 查询软件版本 | 下行 | ENQ | — | ✅ `build_query_software_version` | 空正文 |
| `46` | 查询状态及报警 | 下行 | ENQ | — | ✅ `build_query_status_alarm` | 空正文 |
| `47` | 初始化固态存储 | 下行 | ENQ | — | ✅ `build_init_solid_storage` | 97H 标识符（附录D #120） |
| `48` | 恢复出厂设置 | 下行 | ENQ | — | ✅ `build_reset_frame` | 98H 标识符 |
| `49` | 修改密码 | 下行 | ENQ | — | ✅ `build_change_password_frame` | 03H 标识符 + 新旧密码 2B |
| `4A` | 设置时钟 | 下行 | ENQ | — | ✅ `build_clock_sync_frame` | 时钟校准 |
| `4B` | 设置IC卡状态 | 下行 | ENQ | — | — | 中心站设置遥测站IC卡状态 |
| `4C` | 控制水泵 | 下行 | ENQ | — | — | 控制抽（排）水站水泵开关机/状态自报 |
| `4D` | 控制阀门 | 下行 | ENQ | — | — | 控制取（排）水口管道阀门开关/状态自报 |
| `4E` | 控制闸门 | 下行 | ENQ | — | — | 控制取（排）水口闸门开关/状态自报 |
| `4F` | 水量定值控制 | 下行 | ENQ | — | — | 水量定值控制功能投入/退出 |
| `50` | 查询事件记录 | 下行 | ENQ | — | ✅ `build_query_event_record` | 空正文 |
| `51` | 查询时钟 | 下行 | ENQ | — | ✅ `build_query_clock` | 空正文 |

### 2.3 要素编码

**定义符机制（规约表26）**

每个要素前有 2 字节标识符：**引导符(1B)** + **定义符(1B)**。

定义符编码：高 5 位 = 数据字节数（0~31），低 3 位 = 小数位数（0~7）。

```python
def parse_def_byte(b: int) -> tuple[int, int]:
    return (b >> 3) & 0x1F, b & 0x07
```

**要素标识符表（规约附录C）** — 101 项已全部收录。支持 HEX/BCD 引导符表 `SL651_ELEMENTS` 和 ASCⅡ 标识符表 `SL651_ASCII_ELEMENTS`（101 项，时间步长码 `DRxnn` 由解码器动态识别）。**FF 子标识符**已收录北京水务平台自定义要素（GPRS信号、机箱温度、地温、垂线流速等）及水测家自定义要素。

**负数 BCD 编码（规约 6.6.3.3a）**：首字节 `0xFF` 表示负数。

**状态位解码（规约表58）**：`45H` 要素为 12-bit 压缩位掩码（交流电充电/蓄电池电压/水位超限/流量超限/水质超限/流量仪表/水位仪表/终端箱门/存储器/IC卡功能/水泵工作/剩余水量，共 12 位）。

**F4/F5 数组（规约附录C 表C.1）**：`F4H` 固定 12 字节（12×5min 时段雨量，0.1mm）；`F5H~FCH` 固定 24 字节（12×5min 间隔相对水位，0.01m）。数组长度按规范固定，不采信定义符长度；定义符与规范不符时写入 `DecodedMessage.warnings` 并继续按规范解析。

> 注：福建样本 0x34 帧 F5 定义符为 `0x5C`（声明 11 字节/4 小数），与规范固定 24 字节冲突，疑为厂商非标实现或样本笔误。本工具按规范固定 24B/0.01m 解析并告警；该样本的具体数值语义待与厂商确认。

### 2.4 校验算法

- **算法**: CRC-16/MODBUS (多项式反转 `0xA001`, 初值 `0xFFFF`)，覆盖 7E7E 到结束符（含）
- **字节序**: 大端
- **验证向量**: `crc16(b"123456789") == 0x4B37`

### 2.5 解码器设计

**输入**: 十六进制字符串或 bytes。自动识别 `7E7E`(HEX/BCD) 或 `01`(ASCII, 单 SOH) 起始。

**错误处理**:
- 报文为空 / 非HEX字符 / 奇数长度 / 非7E7E或0101开头 / 正文长度不匹配 → `DecodeError`
- 无效 BCD 数据 → 优雅降级，值显示为 `-`

**输出**: `DecodedMessage` 数据类，含报头信息、要素列表、CRC 信息、逐字节视图、非致命告警 `warnings`（如 F4/F5 定义符与规范不符）。

**流式解析与多包重组**: `feed(bytes) -> list[DecodedMessage]` 支持跨次调用缓冲不完整帧，并按 SYN 帧「包总数/序列号」（表22：3B，高12位总数/低12位序号）重组多包正文（ETB=后续还有包，ETX=最后一包，规约 6.3.2.5）；支持乱序到达与增量喂入。`reset()` 清空状态。

### 2.6 编码器设计

**编码器**: `SL651Encoder(center_addr, station_addr, password, station_type)`

| 方法 | 功能码 | 方向 | 结束符 | 说明 |
|------|--------|------|--------|------|
| `build_timing_frame(elements)` | 0x32 | 上行 | ETX | ✅ 定时报 |
| `build_alarm_frame(elements)` | 0x33 | 上行 | ETX | ✅ 加报报 |
| `build_hourly_frame(levels, inst, v)` | 0x34 | 上行 | ETX | ✅ 小时报（12×F5数组） |
| `build_test_frame(elements)` | 0x30 | 上行 | ETX | ✅ 测试报（正文同定时报） |
| `build_manual_frame(payload)` | 0x35 | 上行 | ETX | ✅ 人工置数报（F2 标识符 + 原编码） |
| `build_init_solid_storage()` | 0x47 | 下行 | ENQ | ✅ 初始化固态存储（97H 标识符） |
| `build_change_password_frame(old, new)` | 0x49 | 下行 | ENQ | ✅ 修改密码（03H 标识符） |
| `build_link_maintain_frame()` | 0x2F | 上行 | ETX | ✅ 链路维持 |
| `build_ascii_frame(elements)` | 0x32 | 上行 | ETX | ✅ ASCII 编码（SOH起始） |
| `build_query_frame()` | 0x37 | 下行 | ENQ | ✅ 查询实时数据（空正文，表42） |
| `build_downlink_query(func)` | 任意 | 下行 | ENQ | ✅ 通用空正文下行查询 |
| `build_query_pump_data/software_version/status_alarm/event_record/clock()` | 44/45/46/50/51 | 下行 | ENQ | ✅ 无参数体查询 |
| `build_query_body(guides)` | 3AH | 下行 | ENQ | ✅ 查询指定要素（正文含引导符） |
| `build_set_param_frame(params, function_code=0x40)` | 0x40/0x42 | 下行 | ENQ | ✅ 参数设置/修改运行参数 |
| `build_read_config_frame(guides, function_code=0x41)` | 0x41/0x43 | 下行 | ENQ | ✅ 读取基本配置/运行参数 |
| `build_clock_sync_frame(dt)` | 0x4A | 下行 | ENQ | ✅ 时钟校准 |
| `build_reset_frame()` | 0x48 | 下行 | ENQ | ✅ 恢复出厂 |
| `build_frame(function_code, body, direction, ascii_mode, end_marker, tx_time)` | 任意 | 任意 | 可指定 | ✅ 通用帧构造（正文 >4095 抛 `EncodeError`） |

**输入格式**: `elements = [(引导符, 值, 数据字节数, 小数位数), ...]`  
**负数编码**: 首字节 `0xFF` + BCD(abs(value))  
**参数校验**: `station_addr` 必须 10 位 hex → 抛 `EncodeError`；BCD 值超限、正文 >4095 字节 → 统一抛 `EncodeError`

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
| `12` | 设置工作模式 (1B) | 下行 | — | ✅ `build_set_work_mode` | 0=兼容/1=自报/2=查询/3=调试 |
| `15` | 设置充值量 (4B BCD) | 下行 | — | ✅ `build_set_recharge` | m³ |
| `16` | 剩余水量报警值 (3B BCD) | 下行 | — | ✅ `build_set_recharge_alarm` | m³ |
| `17` | 水位基值/上下限 (N×7B) | 下行 | — | ✅ `build_set_level_limits` | 第3字节 D7 符号位 |
| `18` | 水压上/下限 (N×8B) | 下行 | — | ✅ `build_set_pressure_limits` | kPa |
| `19/1A` | 水质参数种类及上/下限 | 下行 | — | ✅ `build_set_water_quality` | 5B 位图 + N×4B |
| `1B` | 水量初始值 (N×5B) | 下行 | — | ✅ `build_set_water_amount` | m³ |
| `1C` | 中继引导码长值 (1B BIN) | 下行 | — | ✅ `build_set_relay_code_len` | s |
| `1D` | 中继转发地址 (N×5B) | 下行 | — | ✅ `build_set_relay_addr` | — |
| `1E` | 中继自动切换/自报 (1B) | 下行 | — | ✅ `build_set_relay_auto_switch` | — |
| `1F` | 流量参数上限 (N×5B) | 下行 | — | ✅ `build_set_flow_limits` | 符号/单位在 BYTE5 |
| `20` | 启报阈值及固态间隔 | 下行 | — | ✅ `build_set_report_threshold` | — |
| `30` | IC卡功能有效 | 下行 | — | ✅ `build_set_ic_card_on` | — |
| `31` | 取消IC卡功能 | 下行 | — | ✅ `build_set_ic_card_off` | — |
| `50~65` | 参数查询 | 下行 | — | ✅ `build_query_*` | 查询帧无 AUX |
| `50~65` | 查询响应 | 上行 | ✅ `_parse_query_response` | — | 地址/时钟/模式/水量/状态/事件/中继/流量等 |
| `90` | 复位终端参数和状态 | 下行 | — | ✅ `build_reset` | 01=参数不变/02=恢复出厂 |
| `91` | 清空历史数据单元 | 下行 | — | ✅ `build_clear_history` | D0雨量/D1水位/D2水量 |
| `92/93` | 启动/关闭水泵或阀门 | 下行 | — | ✅ `build_start_pump`/`build_stop_pump` | — |
| `94/95` | 切换通信机/中继工作机 | 下行 | — | ✅ `build_switch_comm`/`build_switch_relay_work` | — |
| `96` | 修改终端密码 | 下行 | — | ✅ `build_change_password` | 2B BCD |
| `90~96` | 控制响应 | 上行 | ✅ `_parse_control_response` | — | 5AH=执行完毕 |
| `A0` | 设置需查询实时种类 | 下行 | ✅ | ✅ `build_set_realtime_kinds` | 2B 位图（表23） |
| `A1` | 设置自报种类及间隔 | 下行 | ✅ | ✅ `build_set_report_kinds` | 2B 位图 + N×2B（表24/25） |
| `A2` | 设置主备信道及中心地址 | 下行 | ✅ | ✅ `build_set_channel` | 类型码+地址 |
| `B0` | 查询/实时值 | 上行 | ✅ | ✅ `build_query_response` | 按命令类型码解析 |
| `C0` | 自报实时数据 | 上行 | ✅ | ✅ `build_self_report_c0` | D+alarm(2B)+state(2B)+Tp(7B) |
| `81` | 自报告警 | 上行 | ✅ | ✅ `build_self_report_81` | 结构同 C0 |
| `82` | 人工置数 | 上行 | ✅ | ✅ `build_self_report_82` | — |
| `83` | 自报图片 | 上行 | ✅ | — | — |
| `84` | 自报电压 | 上行 | ✅ | ✅ `build_self_report_84` | 2B BCD 电压（表B.98，无 Tp） |
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
| `build_self_report_84(voltage)` | ✅ | 自报电压 (AFN=84，表B.98 无 Tp) |
| `build_query_response(func, data)` | ✅ | 查询响应帧 (AFN=B0) |
| `build_set_addr(bytes, pw)` | ✅ | 设置地址 (AFN=10) |
| `build_set_clock(dt, pw)` | ✅ | 设置时钟 (AFN=11)，星期月复合字节 |
| `build_set_work_mode(mode, pw)` | ✅ | 设置工作模式 (AFN=12) |
| `build_set_recharge(amount, pw)` | ✅ | 设置充值量 (AFN=15) |
| `build_set_recharge_alarm(amount_m3, pw)` | ✅ | 剩余水量报警值 (AFN=16) |
| `build_set_level_limits(points, pw)` | ✅ | 水位基值/上下限 (AFN=17) |
| `build_set_pressure_limits(points, pw)` | ✅ | 水压上/下限 (AFN=18) |
| `build_set_water_quality(afn, params, pw)` | ✅ | 水质参数种类及上/下限 (AFN=19/1A) |
| `build_set_water_amount(values, pw)` | ✅ | 水量初始值 (AFN=1B) |
| `build_set_relay_code_len(seconds, pw)` | ✅ | 中继引导码长值 (AFN=1C) |
| `build_set_relay_addr(addr_list, pw)` | ✅ | 中继转发监测站地址 (AFN=1D) |
| `build_set_relay_auto_switch(value, pw)` | ✅ | 中继自动切换/自报 (AFN=1E) |
| `build_set_flow_limits(points, pw)` | ✅ | 流量参数上限值 (AFN=1F) |
| `build_set_report_threshold(category, index, interval_min, threshold, pw)` | ✅ | 启报阈值及固态存储间隔 (AFN=20) |
| `build_set_ic_card_on/off(pw)` | ✅ | IC卡功能 (AFN=30/31) |
| `build_query(afn, data, func_code)` | ✅ | 通用查询帧（下行，无 AUX） |
| `build_query_addr/clock/work_mode/report_kinds/realtime_kinds/recharge/remaining_alarm/event_record/status_alarm/pump_data/relay_code_len/relay_addr/relay_status/flow_limits/channel` | ✅ | 查询类便捷方法 (AFN=50H~65H) |
| `build_query_image(image_no)` | ✅ | 查询实时图像 (AFN=61H) |
| `build_reset(factory_reset, pw)` | ✅ | 复位终端 (AFN=90H) |
| `build_clear_history(rain, level, water, pw)` | ✅ | 清空历史数据 (AFN=91H) |
| `build_start_pump/stop_pump(code, is_valve, pw)` | ✅ | 启停水泵/阀门 (AFN=92/93H) |
| `build_switch_comm/switch_relay_work(machine, pw)` | ✅ | 切换通信机/中继工作机 (AFN=94/95H) |
| `build_change_password(password, pw)` | ✅ | 修改密码 (AFN=96H) |
| `build_set_realtime_kinds(mask, pw)` | ✅ | 设置需查询实时种类 (AFN=A0H) |
| `build_set_report_kinds(mask, intervals, pw)` | ✅ | 设置自报种类及间隔 (AFN=A1H) |
| `build_set_channel(main_type, main_addr, ...)` | ✅ | 设置主备信道及中心地址 (AFN=A2H) |
| `build_param_set_frame(afn, func, data, pw, tp, key1)` | ✅ | 通用参数设置帧模板（PW 校验统一抛 EncodeError） |

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
| `test_sl651_ascii` | SL651 | 规范 ASCII 编码帧编解码（单 SOH + ASCII 字符头 + 4 字符 CRC） |
| `test_sl651_ascii_roundtrip` | SL651 | ASCII 帧编解码往返（地址、密码、功能码、站类、要素值） |
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
| `test_fujian_messages` | SL651 | **23 条福建规定真实报文 CRC + 要素级基线** |
| `test_beijing_messages` | SL651 | **25 条北京水务平台真实报文 CRC + 要素级基线**（10测站/3类报文） |
| `test_simulator_engine_smoke` | 模拟器 | 引擎冒烟测试 |
| `test_hourly_frame_validation` | SL651 | 小时报 12 组校验 |
| `test_recharge_le_bcd` | SL427 | 充值量小端 BCD |
| `test_sl651_truncated_uplink` | SL651 | 截断上行帧抛 DecodeError（非 IndexError） |
| `test_sl427_malformed_bcd` | SL427 | 非法 BCD/最小 L 抛 DecodeError |
| `test_tcp_sender_threadsafe` | 模拟器 | 多线程共享 TcpSender 帧不交错 |
| `test_sl651_hex_type_ff` | SL651 | Hex 型要素 0xFF 不误判负数 |
| `test_sl651_encoder_validation` | SL651 | 编码器定义符/水位/负数/地址校验 |
| `test_sl427_encoder_validation` | SL427 | encode_address/Tp/build_frame/PW 校验 |
| `test_sl427_ff_tp_strip` | SL427 | AFN=FFH 尾部 Tp 剥离 |
| `test_web_api` | Web | /api/decode 400 路径 + 密码脱敏 + SL427 字段 |
| `test_cli_json_masking` | CLI | JSON 输出脱敏（密码/站址截断） |
| `test_simulator_yaml_validation` | 模拟器 | YAML/端口/地址/间隔校验 |
| `test_soil_temp_bounded` | 模拟器 | 墒情温度 5000 步有界 |
| `test_alert_edge_trigger` | 模拟器 | 加报边沿触发 |
| `test_sl651_decode_entry_check` | SL651 | decode(bytes) 入口起始符校验 |
| `test_sl427_comprehensive_offset` | SL427 | 综合参数 0xAA 填充后偏移正确 |
| `test_sl427_signed_bcd_invalid_nibble` | SL427 | 有符号 BCD 非法半字节降级 `-` |
| `test_sl427_invalid_time_display` | SL427 | 非法 BCD 日期占位显示 |
| `test_sl427_invalid_nibble_time` | SL427 | 非法 BCD 半字节时间占位显示（v1.2.6 B1） |
| `test_sl651_f3_image_display` | SL651 | F3 图片要素字节摘要显示，不数值化（v1.2.6 B2） |
| `test_sl651_ascii_reserved_id` | SL651 | ASCII 编码器拒绝保留引导符 ST/TT（v1.2.6 B3） |
| `test_sl651_uniform_report` | SL651 | 0x31 均匀报标识符组一次 + 12 组数据（v1.2.7 C-1） |
| `test_sl651_f5_fixed_length` | SL651 | F5 定义符失配按固定 24B 解析 + 告警（v1.2.7 M-1） |
| `test_sl427_84_no_tp` | SL427 | AFN=84 自报帧仅 2B 电压、无 Tp（v1.2.7 M-2） |
| `test_sl651_bcd_overflow_contract` | SL651 | BCD 超限抛 EncodeError（v1.2.7 M-3） |
| `test_sl427_bcd_overflow_contract` | SL427 | 电压/充值/密码超限抛 EncodeError（v1.2.7 M-3） |
| `test_sl651_body_len_limit` | SL651 | 正文 >4095 抛 EncodeError（v1.2.7 M-5） |
| `test_sl427_short_data_degrade` | SL427 | C0 短数据域降级解析（v1.2.7 L-3） |
| `test_sl427_addr_method` | SL427 | 地址方式1/方式2 判定（v1.2.7 L-4） |
| `test_sl651_ascii_uniform` | SL651 | 0x31 ASCII 均匀报：时间步长码 DRxnn + 单标识符多值数组（v1.2.7） |
| `test_sl651_test_frame` | SL651 | 0x30 测试报编码（正文同定时报） |
| `test_sl651_downlink_queries` | SL651 | 无参数体下行查询帧 37/44/45/46/50/51H（结束符 ENQ） |
| `test_sl651_config_and_manual_frames` | SL651 | 42H 修改运行参数 / 41H·43H 读取配置 / 0x35 人工置数报 |
| `test_sl651_init_storage_and_password` | SL651 | 47H 初始化固态存储（97H 标识符）/ 49H 修改密码（03H 标识符） |
| `test_sl651_func_name_consistency` | SL651 | FUNC_MAP 功能码名称与规约/编码器一致（v1.3.1 M-1） |
| `test_sl651_manual_frame_fujian` | SL651 | 真实福建 0x35 人工置数报 F2 载荷解析（v1.3.1 M-3） |
| `test_sl427_fill_semantics` | SL427 | 0xAA/0xFF 缺测填充全分支降级 `-`（查询/控制/配置/AFN84）（v1.3.2 M-1/M-2） |
| `test_sl651_status_fill` | SL651 | 45H 状态位全 `0xFF`/`0xAA` 填充降级 `-`（v1.3.2 M-1 同类） |

**总计: 61 项**，全部通过。统一入口 `python tests/run_all.py` 依次运行全部套件。

### 7.4 辅助测试套件

| 套件 | 内容 |
|------|------|
| `test_round1_blindspots.py` | 10 项盲区测试（小时报往返/异常、SL427 81/82/84、充值量数值级） |
| `test_simulator_integration.py` | 5 组端到端集成（引擎全链路、雨量加报边沿、站点注册、TcpSender 真实 TCP 收发、0x26 不归零累计） |
| `test_fuzz_decoders.py` | SL651/SL427 解码器变异测试（各 600 次，断言仅抛受控 `DecodeError`）+ 合法帧/合法填充正向断言（v1.3.2 L-4） |
| `test_sl427_param_afn.py` | SL427 参数设置 AFN 16H~20H 数据域布局 + 13 项超限校验 + 10H 地址长度/A2H 信道地址长度校验（v1.3.1 M-4） |
| `test_sl427_query_afn.py` | SL427 查询类 AFN 50H~65H：17 个查询帧结构 + 20 组响应解析 + 0xAA/0xFF 缺测填充容错（v1.3.1 M-2） |
| `test_sl427_control_afn.py` | SL427 控制/配置 AFN 90H~96H、A0H~A2H：编码 + 响应解析 + 7 项超限校验 + 0xAA 填充容错（v1.3.1 M-2） |
| `test_sl651_multipacket.py` | SL651 多包 SYN/ETB 重组：2/3 包、乱序、增量喂入、垃圾字节、单帧直通、ASCII 方向位保留（v1.3.1 L-2） |

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

### 7.3 北京水务报文测试 ⭐

来源：北京水务平台真实报文（2025-01）。

```bash
# 批量验证
python tools/decode_cli.py sl651 --file examples/beijing_messages.txt

# 覆盖 25 条报文，10 个测站，3 类报文：
# 32(定时报) / 33(加报报) / 34(小时报)
# 含 7 个北京水务 FF 自定义子标识符：GPRS信号/机箱温度/地温/垂线流速等
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
| 规范 ASCII 编码帧（单 SOH + ASCII 字符头 + 4 字符 CRC，表16/17） | ✅ |
| 福建规定 23 条真实报文验证 | ✅ |
| 北京水务平台 25 条真实报文验证 | ✅ |
| 北京水务 FF 子标识符（GPRS信号/机箱温度/地温/垂线流速等 7 个） | ✅ |
| SL651 加报报触发要素标识 | ✅ |
| SL651 下行帧正文结构修正（4A 校时/37 查询/48 98H标识） | ✅ |
| SL651 流水号规则（下行=0、2F 不累加） | ✅ |
| SL651 报文标识 12 位宽修正 | ✅ |

### ✅ P3 — 已完成

| 任务 | 状态 |
|------|------|
| SL651 下行帧编码（查询/设置/校时/复位，规约功能码+ENQ结束符） | ✅ |
| Web UI（Flask 单文件解码界面） | ✅ |
| 规范 ASCII 编码帧（单 SOH + ASCII 字符头 + 4 字符 CRC） | ✅ |
| SL427 alarm/state 字节序修正（LE） | ✅ |
| SL427 AFN=81H/84H/B0 数据域结构修正 | ✅ |
| SL427 综合参数/流量/报警位/状态位解析修正 | ✅ |
| SL427 PW 编码格式修正（表9） | ✅ |
| 小时报 F4 雨量组 | ✅ |
| 盲区测试全覆盖（10/10 通过） | ✅ |

### ✅ 已完成（v1.2.8）

| 任务 | 说明 |
|------|------|
| 统一测试入口 + CI | `tests/run_all.py`、`.github/workflows/ci.yml` |
| 模拟器端到端集成测试 | `tests/test_simulator_integration.py`（含真实 TCP 收发） |
| 解码器变异/模糊测试 | `tests/test_fuzz_decoders.py`（SL651/SL427 各 600 次） |
| SL427 参数设置 AFN 16H~20H | 11 个便捷方法 + 数据域布局测试（`tests/test_sl427_param_afn.py`） |

### ✅ 已完成（v1.3.0）

| 任务 | 说明 |
|------|------|
| SL427 查询类 AFN 50H~65H | 17 个查询帧构造 + 20 组响应解析（`tests/test_sl427_query_afn.py`） |
| SL427 控制/配置 AFN 90H~96H、A0H~A2H | 复位/清空/启停泵/切换/改密/实时种类/自报种类/主备信道（`tests/test_sl427_control_afn.py`） |
| SL651 多包 SYN/ETB 重组 | `feed()` 流式 API，按包总数/序列号重组，支持乱序/增量/垃圾字节（`tests/test_sl651_multipacket.py`） |
| SL651 编码器补全 | 0x30/0x35/41H/42H/43H/44H/45H/46H/47H/49H/50H/51H + `build_downlink_query` |
| 模拟器 0x26 累计雨量 | 改为不归零累计（`RainGenerator.total_accum`，上限翻转） |

### ✅ 已完成（v1.3.2）

| 任务 | 说明 |
|------|------|
| 审计 v2.4 修复 | M-1 缺测填充全分支（查询/控制/配置/AFN51 + SL651 45H）/ M-2 AFN=84 填充 / L-1~L-5 文档与测试 |
| 测试增强 | 主套件 59 → 61 项（填充全分支语义 + SL651 45H）；变异套件补合法帧正向断言 |

### ✅ 已完成（v1.3.1）

| 任务 | 说明 |
|------|------|
| 审计 v2.3 修复 | M-1 FUNC_MAP 名称 / M-2 SL427 0xAA 填充 / M-3 人工置数 F2 契约 / M-4 地址长度校验 |
| 审计 v2.3 L 级修复 | L-1 5CH 名称 / L-2 ASCII 方向位 / L-3 死键 / L-4 0x26 量程注释 / L-5 示例注释 / L-6 文档计数 |
| 测试增强 | 主套件 57 → 59 项；辅助套件补 0xAA 填充容错、地址长度校验、ASCII 方向位 |

### ⬜ 远期（P4）

| 任务 | 说明 |
|------|------|
| SL427 5CH 历史日记录响应 | 所给规约文本/PDF 正文未定义字段，暂以字节摘要显示 |
| SL651 41H/42H/43H 参数标识符细化 | 当前按附录D 引导符列表构造，具体参数定义未全量收录 |
| SL427 下行参数/查询帧解码 | 下行帧当前仅显示「下行报文」摘要，未回显命令数据域 |
| 模拟器 MQTT broker 联调 | 已覆盖内存/TCP 全链路；MQTT 需 mqttx CLI 环境 |
| ~~45H 状态位 32 位全量~~ | **不存在**：规约表58 仅定义 BIT0~BIT11，BIT12~31 为保留，当前 12 位实现与规约一致 |
| ~~SL427 ASCII 编码帧~~ | **不存在**：SL427-2021 全文无 ASCII/字符编码，帧结构固定为 68H…16H 二进制 |
