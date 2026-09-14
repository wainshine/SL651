# SL651 水文规约工具包 v1.3.1

基于《水文监测数据通信规约 SL651-2014》和《水资源监测数据传输规约 SL/T 427-2021》实现的 Python 工具包。

**两大核心能力**：报文解码 + 设备模拟。**支持 HEX/BCD 和 ASCII 两种编码**，**上行/下行全功能编解码**。

---

## 目录结构

```
sl651-toolkit/
├── sl651/                      # SL651 协议核心
│   ├── README.md
│   ├── bcd.py                  # BCD 编解码
│   ├── crc.py                  # CRC-16/MODBUS + CRC8
│   ├── constants.py            # 101 要素表、FF/ASCII 子标识符、帧结构常量
│   ├── decoder.py              # 解码器（HEX/BCD + ASCII，定义符动态解析）
│   └── encoder.py              # 编码器（上行 5 类 + 下行 4 类 + ASCII）
├── sl427/                      # SL427 协议核心
│   ├── README.md
│   ├── constants.py            # 控制功能码(16)、AFN(30)、告警/终端状态
│   ├── decoder.py              # 68H 帧解析器（AUX 分离）
│   └── encoder.py              # 68H 帧编码器（自报 5 类 + 参数 6 类）
├── simulator/                  # 设备模拟器
│   ├── README.md
│   ├── base_station.py         # 站点基类
│   ├── generators.py           # 水位/雨量/墒情数据生成器
│   ├── water_level_station.py  # 水位站 N(7,3)
│   ├── rain_station.py         # 雨量站（含加报）
│   ├── soil_station.py         # 墒情站
│   ├── sender.py               # MqttxSender + TcpSender（重连）
│   └── engine.py               # 定时循环引擎（含加报机制）
├── tools/                      # CLI 工具
│   ├── README.md
│   ├── decode_cli.py           # 解码 CLI（sl651/sl427/text/json）
│   └── simulate_cli.py         # 模拟器 CLI（mqtt/tcp/YAML）
├── web/                        # Web 界面
│   ├── README.md
│   └── app.py                  # Flask 单文件解码界面
├── examples/                   # 示例报文与配置
│   ├── sample_messages.txt     # 基础示例
│   ├── fujian_messages.txt     # 福建规定 23 条
│   ├── beijing_messages.txt    # 北京水务平台 25 条
│   ├── stations.yaml           # 多站点配置
│   └── mqttx_subscribe.txt     # MQTTX 订阅参考
├── tests/
│   ├── run_all.py              # 统一测试入口（8 套件）
│   ├── test_sl651.py           # 主测试 59 项
│   ├── test_round1_blindspots.py    # 盲区测试 10 项
│   ├── test_simulator_integration.py # 模拟器端到端集成
│   ├── test_fuzz_decoders.py   # 解码器变异/流式健壮性
│   ├── test_sl427_param_afn.py # SL427 参数 AFN 16H~20H
│   ├── test_sl427_query_afn.py # SL427 查询 AFN 50H~65H
│   ├── test_sl427_control_afn.py # SL427 控制/配置 AFN 90H~A2H
│   └── test_sl651_multipacket.py # SL651 多包 SYN/ETB 重组
├── docs/
│   └── project.md              # 项目规格说明书
├── audit/                      # 审计报告 v1.1~v2.3
├── requirements.txt            # PyYAML>=6.0 + flask
└── README.md
```

> 仓库根另有 `.github/workflows/ci.yml`（CI，Python 3.10/3.11/3.12）。

## 环境要求

- Python 3.10+
- `PyYAML>=6.0`（仅多站点配置需要）
- 模拟器 MQTT 模式需要系统安装 `mqttx` CLI：
  ```bash
  # macOS arm64
  curl -sL https://github.com/emqx/MQTTX/releases/download/v1.13.0/mqttx-cli-macos-arm64 -o /usr/local/bin/mqttx && chmod +x /usr/local/bin/mqttx
  # Linux x64
  curl -sL https://github.com/emqx/MQTTX/releases/download/v1.13.0/mqttx-cli-linux-x64 -o /usr/local/bin/mqttx && chmod +x /usr/local/bin/mqttx
  ```

---

## 一、报文解码器

### 1.1 CLI 使用

```bash
# SL651 解码（HEX/BCD 或 ASCII 编码）
python tools/decode_cli.py sl651 --hex "7E7E25XXXXXXXXXX00..."

# SL427 解码
python tools/decode_cli.py sl427 --hex "681568..."

# 文件批量解码
python tools/decode_cli.py sl651 --file messages.txt

# JSON 输出
python tools/decode_cli.py sl651 --hex "..." -o json
```

### 1.2 解码输出示例

```
========================================================================
原始报文: 7E7E25XXXXXXXXXX0000320030020C06230601010314F1F1XXXXXXXXXX4BF0F0...
------------------------------------------------------------------------
中心站地址    : 25**
遥测站地址    : 1234******
功能码        : 0x32 (定时报)
方向          : 上行（遥测站→中心站）
正文长度      : 48 字节
流水号        : 0C06
发报时间      : 2023-06-01 01:03:14
测站类别      : 4B (水库)
观测时间      : 2023-06-01 01:00
编码方式      : BCD
CRC 校验      : 通过 (接收=0x5AC6, 计算=0x5AC6)
------------------------------------------------------------------------
要素数据 (5 项):
  编码   名称                           值                 单位       原始HEX
  20    当前降水量                        0.0                 mm       000000
  3B    坝上水位                         37.865              m        00037865
  22    5分钟雨量                        0.0                 mm       000000
  26    累计雨量                         0.0                 mm       000000
  38    电池电压                         12.85               V        1285
========================================================================
```

### 1.3 Python API

```python
from sl651 import SL651Decoder
from sl427 import SL427Decoder

# SL651
r = SL651Decoder().decode_hex("7E7E...")
print(r.station_addr, r.function_name, r.tx_time_display)
for e in r.elements:
    print(f"  [{e.code}] {e.name}: {e.display_value}")

# SL651 流式解析 + 多包 (SYN/ETB) 自动重组
dec = SL651Decoder()
for msg in dec.feed(stream_bytes):   # 可分多次喂入
    print(msg.function_name, len(msg.elements))

# SL427
r = SL427Decoder().decode_hex("68...")
print(r.afn_name, r.direction)
for e in r.elements:
    print(f"  {e.name}: {e.value} {e.unit}")
```

---

## 二、报文编码器

### 2.1 SL651 编码

| 方法 | 功能码 | 方向 | 结束符 | 说明 |
|------|--------|------|--------|------|
| `build_timing_frame(elements)` | 0x32 | 上行 | ETX | 定时报 |
| `build_alarm_frame(elements)` | 0x33 | 上行 | ETX | 加报报 |
| `build_hourly_frame(levels, inst, v)` | 0x34 | 上行 | ETX | 小时报（含 12×F5 水位） |
| `build_test_frame(elements)` | 0x30 | 上行 | ETX | 测试报（正文同定时报） |
| `build_link_maintain_frame()` | 0x2F | 上行 | ETX | 链路维持 |
| `build_ascii_frame(elements)` | 0x32 | 上行 | ETX | ASCII 编码（SOH 起始） |
| `build_query_frame()` | 0x37 | 下行 | ENQ | 查询所有实时数据 |
| `build_downlink_query(func)` | 任意 | 下行 | ENQ | 通用空正文下行查询 |
| `build_query_pump_data()` 等 | 44/45/46/50/51 | 下行 | ENQ | 水泵/版本/状态/事件/时钟查询 |
| `build_query_body(guides)` | 0x3A | 下行 | ENQ | 查询指定要素（正文含引导符） |
| `build_manual_frame(payload)` | 0x35 | 上行 | ETX | 人工置数报 |
| `build_init_solid_storage()` | 0x47 | 下行 | ENQ | 初始化固态存储 |
| `build_change_password_frame(old, new)` | 0x49 | 下行 | ENQ | 修改密码 |
| `build_set_param_frame(params, function_code=0x40)` | 0x40/0x42 | 下行 | ENQ | 参数设置/修改运行参数 |
| `build_read_config_frame(guides, function_code=0x41)` | 0x41/0x43 | 下行 | ENQ | 读取基本配置/运行参数 |
| `build_clock_sync_frame(dt)` | 0x4A | 下行 | ENQ | 时钟校准 |
| `build_reset_frame()` | 0x48 | 下行 | ENQ | 恢复出厂 |
| `build_frame(function_code, body, ...)` | 任意 | 任意 | 可指定 | 通用帧构造（正文 >4095 抛 EncodeError） |

### 2.2 SL427 编码

| 方法 | AFN | 方向 | 说明 |
|------|-----|------|------|
| `build_heartbeat(type)` | 0x02 | 上行 | 链路检测 |
| `build_self_report_c0(func, data)` | 0xC0 | 上行 | 自报实时数据 |
| `build_self_report_81(func, data)` | 0x81 | 上行 | 自报告警 |
| `build_self_report_82(func, data)` | 0x82 | 上行 | 人工置数 |
| `build_self_report_84(voltage)` | 0x84 | 上行 | 自报电压（表B.98，无 Tp） |
| `build_query_response(func, data)` | 0xB0 | 上行 | 查询响应 |
| `build_param_set_frame(afn, func, data, pw, tp, key1)` | 10~4F | 下行 | 通用参数设置 |
| `build_set_addr(bytes)` | 0x10 | 下行 | 设置站址 |
| `build_set_clock(dt)` | 0x11 | 下行 | 设置时钟 |
| `build_set_work_mode(mode)` | 0x12 | 下行 | 设置工作模式 |
| `build_set_recharge(amount)` | 0x15 | 下行 | 设置充值量 |
| `build_set_recharge_alarm(m3)` | 0x16 | 下行 | 剩余水量报警值 |
| `build_set_level_limits(points)` | 0x17 | 下行 | 水位基值/上下限 |
| `build_set_pressure_limits(points)` | 0x18 | 下行 | 水压上/下限 |
| `build_set_water_quality(afn, params)` | 0x19/0x1A | 下行 | 水质参数上/下限 |
| `build_set_water_amount(values)` | 0x1B | 下行 | 水量初始值 |
| `build_set_relay_code_len(seconds)` | 0x1C | 下行 | 中继引导码长值 |
| `build_set_relay_addr(addrs)` | 0x1D | 下行 | 中继转发地址 |
| `build_set_relay_auto_switch(value)` | 0x1E | 下行 | 中继自动切换/自报 |
| `build_set_flow_limits(points)` | 0x1F | 下行 | 流量参数上限值 |
| `build_set_report_threshold(...)` | 0x20 | 下行 | 启报阈值/固态间隔 |
| `build_set_ic_card_on()` | 0x30 | 下行 | IC卡有效 |
| `build_set_ic_card_off()` | 0x31 | 下行 | 取消IC卡 |

---

## 三、设备模拟器

### 3.1 CLI 使用

```bash
# MQTT 模式
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto mqtt --broker 192.168.1.100:1883 --interval 300

# TCP 模式
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto sl651 --target 192.168.1.100:5001 --interval 300

# 启用加报
python tools/simulate_cli.py --type rain --addr 1234567892 \
    --proto mqtt --broker 127.0.0.1:1883 --enable-alert

# 多站点 YAML
python tools/simulate_cli.py --config examples/stations.yaml
```

### 3.2 站点类型

| 站点 | 模拟要素 | 要素码 | 加报触发 |
|---|---|---|---|
| 水位站 | 瞬时河道水位、电池电压 | `0x39`、`0x38` | 水位变化 > 阈值 |
| 雨量站 | 日降水量、1h雨量、当前降水量、累计雨量、电压 | `0x1F`、`0x1A`、`0x20`、`0x26`、`0x38` | 降雨状态 |
| 墒情站 | 10/20/30/40cm 含水量、电压 | `0x10`、`0x11`、`0x12`、`0x13`、`0x38` | — |

### 3.3 Web 解码界面

```bash
python web/app.py
# 浏览器打开 http://localhost:5050
# 粘贴 hex → 选协议 → 解析
```

---

## 四、运行测试

```bash
# 一键运行全部套件（推荐）
python tests/run_all.py

# 或单独运行
python tests/test_sl651.py            # 59 项主测试
python tests/test_round1_blindspots.py  # 10 项盲区测试
```

- `run_all.py` 共 8 套件：主套件 59 项 + 盲区 10 项 + 模拟器集成 5 组 + 变异 3 组 + SL427 参数 11 组 + 查询 20 组 + 控制 9 组 + SL651 多包 5 组
- 23 条福建 + 25 条北京真实报文 CRC + 要素级验证
- CI：`.github/workflows/ci.yml`（Python 3.10/3.11/3.12 自动运行 `tests/run_all.py`）

---

## 五、版本历史

- **v1.3.1**：审计 v2.3 修复版（4M+6L）
  - M-1: `FUNC_MAP` 0x38~0x51 功能码名称按规约正文重写，补齐 0x39/0x44/0x4B~0x4F（原 0x44 显示「未知」、0x45~0x51 名称错误）
  - M-2: SL427 查询/控制响应对规约合法 `0xAA`/`0xFF` 缺测填充降级为 `-`，不再抛 `DecodeError`
  - M-3: SL651 人工置数报 `F2` 契约统一（F2 后为原编码载荷，无定义符），福建 0x35 帧恢复 1 要素（原 0 要素静默丢失）
  - M-4: SL427 `build_set_addr`（固定 5B）/`build_set_channel`（按类型码校验地址长度）补数据域长度校验
  - L-1: `AFN_MAP[0x5C]` 更正为「查询终端机历史日记录」
  - L-2: ASCII 多包重组保留方向位（原恒判上行）
  - L-3: 移除 `SL651_ASCII_ELEMENTS` 死占位键 `DRxnn`（动态识别，102 → 101 项）
  - L-4: 0x26 累计雨量注释/文档对齐实际量程 `N(5,1)`（99999.9mm）
  - L-5: `examples/fujian_messages.txt` 注释同步更正的功能码名称
  - L-6: `handoff_test.md` 历史测试计数标注为快照
  - 测试: 主套件 57 → 59 项（功能码名称一致性 / 人工置数 F2 契约）；辅助套件补 0xAA 填充容错与地址长度校验
  - 文档一致性 D-1~D-6 修正

- **v1.2.7**：审计 v2.2 修复版（1C+5M+7L 缺陷修复 + 真实报文要素级测试）
  - C-1: 0x31 均匀报实现「标识符组一次 + 多组重复数据」解析（福建帧恢复 12/12 组，原丢失 11 组）
  - M-1: F4/F5~FC 数组按规范固定 12B/24B 解析，不再采信失配定义符；不符时写入 `warnings`，消除截断与垃圾要素
  - M-2: SL427 84H 自报帧按规范表B.98 修正为「仅 2B 电压、无 Tp」，移除误导性的 `tp` 参数与对应解码分支（审计原述与规约冲突，以规约 B.98 为准）
  - M-3: BCD 值超限统一抛 `EncodeError`（SL651/SL427，原泄漏 `ValueError`）
  - M-4: 福建 23 条 / 北京 25 条真实报文增加「要素总数 + 首末要素值」基线断言（原仅验 CRC）
  - M-5: `build_frame`/`build_ascii_frame` 校验正文 ≤4095，超限抛 `EncodeError`（原静默掩码）
  - L: 加报边沿测试驱动真实 `_run`；无效 BCD 降级断言强化；SL427 短数据域降级；地址方式判定文档化；死常量标注；PW key1/溢出校验
  - 收尾: SL427 `DecodedMessage` 增加 `warnings` 通道（短数据域降级可见）；0x31 ASCII 均匀报识别时间步长码 `DRxnn` 并支持单标识符多值数组
  - 文档一致性 D-1~D-11 修正；测试 44 → 53 项

- **v1.3.0**：SL427 全 AFN + SL651 编码器补全 + 多包重组
  - 功能: SL427 查询类 AFN 50H~65H 查询帧构造 + 响应解析（地址/时钟/模式/水量/状态/水泵/中继等）
  - 功能: SL427 控制/配置 AFN 90H~96H、A0H~A2H（复位/清空/启停泵/切换/改密/实时种类/自报种类/主备信道）
  - 功能: SL427 查询响应补齐 53/57/58/59/5A/5D/63/64/65H（自报种类/水位/水压/水质/事件/中继/流量/信道）
  - 功能: SL427 `AFN_MAP` 扩至 61 项，新增参数种类/事件记录/水质参数表；补 5CH 历史日记录查询帧（响应字段规约未定义，暂以字节摘要显示）
  - 功能: SL651 多包 SYN/ETB 流式重组 `SL651Decoder.feed()`（表22：包总数/序列号，支持乱序/增量/垃圾字节）
  - 功能: SL651 编码器补 0x30 测试报、0x35 人工置数报、41H/42H/43H 配置、44H/45H/46H/50H/51H 查询、47H 初始化固态、49H 修改密码 + 通用 `build_downlink_query`
  - 修复: 模拟器 0x26 降水量累计值改为不归零累计（原用日累计近似，代码 TODO 闭环）
  - 测试: 主套件 53 → 57 项；辅助套件 4 → 7（新增 SL427 参数/查询/控制 AFN、SL651 多包重组）；`run_all.py` 8/8

- **v1.2.8**：工程化 + 测试深度 + SL427 参数 AFN 扩展
  - 工程化: 统一测试入口 `tests/run_all.py` + GitHub Actions CI（Python 3.10/3.11/3.12）
  - 测试: 新增模拟器端到端集成（含 TcpSender 真实 TCP 收发）与解码器变异测试（SL651/SL427 各 600 次）
  - 功能: SL427 参数设置 AFN 16H~20H 共 11 个便捷方法（数据域按规约表14~21 布局）
  - 规约核查: 关闭「SL427 ASCII 编码帧」（规约不存在）与「45H 32 位」（表58 仅定义 12 位）两个伪需求
  - 测试: 主套件 53 项 + 4 个辅助套件（`run_all.py` 5/5）

- **v1.2.6**：主会话 4 代自审计修复版（文档一致性修正 + 3 项缺陷修复）
  - 文档：根 README/toolkit README/handoff_test 测试计数滞后修正（24/25 → 44 项）、handoff_main 行号漂移 2 处、sl651 README 参数名 `func` → `function_code`
  - B1: SL427 `_fmt_time_427` 非法 BCD 半字节被 `or 0` 静默归零产生假时间 → 统一显示"无效时间(...)"占位
  - B2: SL651 F3 图片要素不再数值化（原显示天文数字），改为字节数 + hex 预览
  - B3: `build_ascii_frame`/`build_ascii_body` 拒绝保留引导符 ST/TT，抛 EncodeError
  - N3: 编码器 obs_time/tx_time 参数类型校验统一抛 EncodeError（原误传 str 泄漏 AttributeError）
  - 文档补充: README §2.1 编码器表补 build_query_body/build_frame 两行；handoff_audit/handoff_test 基线版本同步
  - 测试: 41 → 44 项（test_sl427_invalid_nibble_time / test_sl651_f3_image_display / test_sl651_ascii_reserved_id）

- **v1.2.5**：审计 v2.1 修复版（4H+12M+20L 缺陷修复）+ Web 界面重写（亮色监控台风格）
  - H: SL651 截断上行帧 IndexError、SL427 非法 BCD ValueError 泄漏、SL427 最小 L 校验、TcpSender 多线程加锁
  - M: Hex 型要素 0xFF 误判负数、ASCII CRC/站类异常逃逸、编码器参数校验统一 EncodeError、AFN=FFH Tp 剥离
  - M: 模拟器 YAML 配置校验、墒情温度漂移修复、加报边沿触发、TCP 缺省端口 5001
  - M: Web /api/decode 输入校验 400、CLI JSON 输出与 Web 密码脱敏
  - L: byte_map 高亮死代码修复、byte_table SYN 偏移、SL427 to_dict 补帧长度、CLI --raw-only 死参数移除
  - 测试: 25 → 41 项；文档一致性修正 8 处（ASCII 102 项/AFN 30 项/FUNC_MAP 23 项等）
  - 补充: decode() 入口起始符校验、综合参数 0xAA 填充偏移、有符号 BCD 非法半字节降级、非法 BCD 时间占位显示

- **v1.2.4**：审计 v2.0 修复版（3M+13L 缺陷修复）

- **v1.2.3**：审计 v1.9 修复版（28 项缺陷修复）
  - C-1: SL651 ASCII 帧按规范表16/17 重构（单 SOH + ASCII 字符头 + 4 字符 CRC + ST/TT 标识符）
  - C-2: SL427 AFN=81H 告警帧数据域顺序修正（alarm 在前）
  - SL427: 84H 电压帧数据域仅 2B（去 alarm/state/Tp）、B0 响应帧尾部 4B 状态字处理
  - SL427: 综合参数 bit0 水质纳入、bit3 修正气象、上行去误调用；流量按表35 解析符号/单位；PW 编码按表9
  - SL427: 报警位补 D9 温度超限、状态位 D2/D3 语义修正、确认帧解析
  - SL651: 下行帧 4A/37/48 正文结构修正、流水号规则（下行=0, 2F不累加）；加报报触发要素；小时报 F4 雨量
  - SL651: 报文标识 12 位宽修正、SYN 多包偏移、F0F0 偏移修正
  - 模拟器: station_type 遮蔽修复、地址校验、Web 安全标注
  - 测试: round1 盲区测试修复（从 5 项恒失败→全覆盖）

- **v1.2.2**：缺陷修复版
  - SL427：AFN=0x81/0x82/0x84 解码支持 alarm/state/Tp 提取（与 C0 一致）
  - SL427：AFN=0x84 电压 BCD 解码修正（bcd_bytes_to_int_le）
  - SL427：alarm/state 字节序修正（LE 编码，解码端统一为 LE）
  - SL651：小时报 F5 负数水位编码防崩溃
  - SL651：BCD/Hex 解码值类型统一为 int/float（与 ASCII 一致）

- **v1.2.1**：北京水务报文验证
  - 北京水务平台 25 条真实报文（8 测站/3 类报文）全部 CRC 通过
  - 新增 7 个北京水务 FF 子标识符（GPRS信号/机箱温度/地温/垂线流速）
  - 24 项测试覆盖

- **v1.2.0**：功能补全版
  - SL651：下行帧编码（查询/设置/校时/复位，规约定义功能码+ENQ结束符）、ASCⅡ编码帧（SOH 起始）
  - SL427：编码器补全（自报 5 类 + 参数设置 6 类）、`build_set_clock` 星期月复合字节
  - 模拟器加报机制（雨量/水位触发 0x33 帧）、Web 解码界面
  - 福建规定 23 条真实报文验证，21 项测试

- **v1.1.0**：部分参考 njnrs 实现重构
  - 解码器：定义符动态解析、101 要素表、FF 子标识符、状态位解码
  - 新增 SL427 解码器（68H 帧 + CRC8）
  - 模拟器：拆分 sender/engine，MQTT 改用 mqttx CLI，新增 TCP 直连模式
  - CRC 修正为 CRC-16/MODBUS，负数 BCD 编码修复

- **v1.0.0**：初始版本
