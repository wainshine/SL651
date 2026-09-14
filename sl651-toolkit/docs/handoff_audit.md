# SL651-Toolkit 审计交接文档

> 角色：代码审计 2 代  
> 接棒时间：2026-07-01  
> 基线版本：v1.3.1  
> 接手前必读：`docs/project.md` + `docs/handoff_main.md` + 本文档

---

## 一、审计角色定义

**职责**：只审不修。逐轮审查代码与规约的一致性，发现缺陷、记录缺陷、跟踪闭环。不修改任何源文件。

**与开发/测试的关系**：

```
开发 → 实现功能 → 代码基线
  ↓
审计 → 发现缺陷 → audit_report_v1.X.md
  ↓
测试 → 验证缺陷 → 开发修复 → 回归
  ↓
审计 → 复核闭环 → 报告更新
```

**权限边界**：
- ✅ 读取所有源码、规范文档、示例报文
- ✅ 运行测试脚本、解码工具验证行为
- ✅ 构造性回放验证（实际执行代码，验证缺陷存在性）
- ✅ 写审计报告到 `audit/audit_report_v1.X.md`
- ❌ 不修改任何 `.py` 源文件
- ❌ 不修改 `project.md` / `README.md` / 测试文件
- ❌ 不提交代码、不执行部署

---

## 二、审计参考依据

按优先级排列：

| 优先级 | 文档 | 频次 | 用途 |
|--------|------|------|------|
| P0 | `行业规范/水文监测数据通信规约SL651-2014.txt` | 首轮一次性 | SL651 帧结构、功能码、要素编码、CRC 定义 |
| P0 | `行业规范/水资源监测数据传输规约SL427-2021.txt` | 首轮一次性 | SL427 帧结构、AFN 定义、控制域、地址域、Tp、数据域格式 |
| P0 | `docs/project.md` | 每轮 | 需求基线，实现范围矩阵，测试清单 |
| P1 | 前期审计报告 `audit/audit_report_v1.*.md` | 每轮 | 已知缺陷上下文，避免重复审计 |
| P1 | `docs/handoff_main.md` | 每轮 | 开发侧最新能力清单与设计决策 |
| P1 | `docs/handoff_test.md` | 每轮 | 测试侧盲区标记与测试覆盖分析 |
| P2 | 真实报文 `examples/fujian_messages.txt` / `examples/beijing_messages.txt` | 每轮 | CRC 验证基准 |

> 两个规范文件内容固定不变，首次审计通读建立基线认知后，后续轮次只需按需查阅具体条文。

---

## 三、审计方法论

### 3.1 四层审计模型

每轮审计必须按顺序覆盖四层：

```
Layer 1: 规约条文比对    ← 代码常量/算法是否与规约表一致
Layer 2: 需求实现对照    ← project.md 标记的功能是否都实现了
Layer 3: 构造性回放验证  ← 实际执行代码，检查行为正确性（最关键）
Layer 4: 历史缺陷复核    ← 上一轮缺陷是否修复到位，有无引入新问题
```

### 3.2 Layer 1 —— 规约条文比对

**做什么**：逐行比对常量定义、算法实现、帧结构偏移与规约白纸黑字的表/章节。

**SL651 重点比对项**：

| 代码位置 | 规约参考 | 核查要点 |
|----------|----------|----------|
| `sl651/constants.py:37` FUNC_MAP | 附录B 表B.1 | 功能码值与描述是否一一对应 |
| `sl651/constants.py:55` STATION_TYPE | 附录A 表A.1 | 站分类码 HEX 值 |
| `sl651/constants.py:117` SL651_ELEMENTS | 附录C 表C.1 | 引导符、标识符、数据定义（101 项） |
| `sl651/constants.py:227` SL651_ASCII_ELEMENTS | 附录C ASCⅡ列 | 标识符 ASCⅡ 字符 |
| `sl651/constants.py:95` parse_def_byte | §6.6.3.2 表26 | 高5位字节数 + 低3位小数位 |
| `sl651/crc.py:12` crc16 | §6.5.2 表20 | 多项式 X16+X15+X2+1、反射 0xA001、初值 0xFFFF |
| `sl651/encoder.py:62` build_frame | §6.5.2 表20/表21 | 上行 `[中心][站址]` vs 下行 `[站址][中心]`、结束符 |
| `sl651/decoder.py:246` decode | §6.5.2 表20/表21 | 帧偏移、方向解析、CRC 覆盖范围 |
| `sl651/encoder.py:19` _make_def_byte | §6.6.3.2 表26 | 定义符编码公式 |
| `sl651/encoder.py:23` _encode_bcd | §6.6.3.3a | 负数 FF 前缀 |
| `sl651/decoder.py:506` _parse_status | 表58 | 12-bit 状态位映射 |
| `sl651/decoder.py:446` _parse_ascii_elements | §6.4 表16 | ASCII 空格分隔、F1F1/F0F0 处理 |
| `sl651/decoder.py:524` _parse_f4_array | 附录C F4H | 12 组 1B HEX 雨量 |
| `sl651/decoder.py:543` _parse_f5_array | 附录C F5H | 12 组 2B HEX 水位 |

**SL427 重点比对项**：

| 代码位置 | 规约参考 | 核查要点 |
|----------|----------|----------|
| `sl427/constants.py:23` AFN_MAP | 附录A 表A.1 | AFN 值与功能定义 |
| `sl427/constants.py:84` CTRL_FUNC_MAP | §6.3.3.3 表5/表6 | 命令与类型码定义、byteLen/decimal/signed |
| `sl427/constants.py:104` ALARM_BITS | §7.3.14 | 14 位告警位映射 |
| `sl427/constants.py:120` TERMINAL_BITS | §7.3.14 | 7 位终端状态映射 |
| `sl427/constants.py:138` parse_ctrl | §6.3.3.3 表4 | DIR/DIV/FCB/命令码 位布局 |
| `sl427/decoder.py:201` _format_addr | §6.3.3.4 表7/表8 | 方式1(BCD+BIN LE) / 方式2(00H+nibble-packed) |
| `sl427/encoder.py:23` encode_address | §6.3.3.4 | A1=3B BCD + A2=2B BIN LE |
| `sl427/encoder.py:45` encode_tp | §6.3.3.8 表10 | 秒/分/时/日/月/年 BCD + 延时 BIN |
| `sl427/crc` → `sl651/crc.py:34` crc8 | §6.3.3.5 | 多项式 X7+X6+X5+X2+1=0xE5、初值 0x00 |
| `sl427/encoder.py:222` build_set_clock | §7.2.3 表12 | 星期月复合字节 D5~D7=星期、D4~D0=月 |
| `sl427/encoder.py:236` build_set_recharge | §7.2.5 表13 | 4B BCD 小端、范围 0~99999999 m³ |
| `sl427/encoder.py:232` build_set_work_mode | §7.2.4 | 00=兼容/01=自报/02=查询应答/03=调试 |

### 3.3 Layer 2 —— 需求实现对照

**做什么**：对照 `project.md` 中的功能矩阵，逐行核实代码是否实现。

**要点**：
- §2.2 功能码矩阵：每个标记 ✅ 的行对应的解码/编码方法是否存在
- §2.6 编码器方法表：每个方法是否可用
- §3.2 SL427 AFN 矩阵：同理
- §4 模拟器：站点模型、发送器、引擎、CLI 是否齐全
- §7 测试清单：测试函数与实际实现的覆盖关系

### 3.4 Layer 3 —— 构造性回放验证（最关键）

**为什么关键**：v1.1~v1.7 共 7 轮审计只做了静态阅读，漏掉了：
- C-1：模拟器引擎 `AttributeError`，启动即崩溃（7 轮均判"✅"）
- M-1：小时报 5 组输入 CRC 通过但要素全丢（CRC 自洽掩盖错误）
- M-2：充值量 BCD 字节序大端/小端反（测试仅验证 CRC）

**必须执行的回放验证清单**：

#### 3.4.1 编码器回放
```python
# 对每个编码器方法：编码 → 立即解码 → 验证
# 不仅仅是 CRC 通过，还要验证数据值

# 示例：充值量
f = enc.build_set_recharge(1234.0)
# 验证：数据域字节序 = 34 12 00 00（小端）
# 验证：LE 解码值 = 1234

# 示例：小时报（12 组）
f = enc.build_hourly_frame([...12个水位值...], inst_level, voltage)
# 验证：CRC 通过 + elements >= 14
# 反例：5 组 → 应报错或 CRC 不通过
```

#### 3.4.2 解码器回放
```bash
# 真实报文批量解码
python tools/decode_cli.py sl651 --file examples/fujian_messages.txt
python tools/decode_cli.py sl651 --file examples/beijing_messages.txt
# 验证：失败数 = 0

# 异常报文不崩溃
# 构造空报文、奇数字节、非7E7E开头、畸形L值 → 应抛 DecodeError，不抛其他异常
```

#### 3.4.3 模拟器端到端
```python
# 引擎 add_station 不崩
from simulator import WaterLevelStation, MqttxSender
from simulator.engine import SimulatorEngine
engine = SimulatorEngine(MqttxSender('127.0.0.1', 1883))
ws = WaterLevelStation('1234567890', base_level=5.0)
engine.add_station(ws, center_addr=1, ...)  # 不抛异常

# 生成的帧可解码且 CRC 通过
elements = ws.generate_elements()
encoder = SL651Encoder(...)
frame = encoder.build_timing_frame(elements, ...)
r = SL651Decoder().decode(frame)
assert r.crc_ok
```

#### 3.4.4 边界条件
```python
# 串号：编码多帧，验证串号单调递增且在 1~65535 范围
# 负数 BCD：编码 -0.345 → 解码 → 值 = -0.345
# BCD 溢出：传超大值 → 应抛 ValueError
# 空输入：空bytes → DecodeError
```

### 3.5 Layer 4 —— 历史缺陷复核

**做什么**：打开上一轮审计报告，逐条检查：
- 每条缺陷是否已修复 → 验证修复方案正确且无副作用
- 修复是否引入了新缺陷 → 回放相关路径
- 修复声明是否真正落实 → 不信任报告自我声明，实际验证

**v1.8 典型案例**：v1.7 的 L-3 声称"project.md 已修正测试计数"，但实际仍为 21，修复声明未落实。

---

## 四、审计报告编写规范

### 4.1 文件命名

```
audit/audit_report_v1.X.md
```

版本号 X 递增。**绝不覆盖历史报告**。

### 4.2 报告结构（固定模板）

```markdown
# SL651-Toolkit 代码审计报告 v1.X

> 审计日期、规范、文档、审计方式、范围

## 一、审计结论总览
| 类别 | 数量 | 状态 |
表：严重(C)/中等(M)/轻微(L) 各几项，已修复/新增/沿用

## 二、严重缺陷（Critical）
每条：源码位置 + 问题描述 + 规约依据 + 实际验证结果 + 影响范围 + 漏报原因

## 三、中等缺陷（Medium）
同上

## 四、轻微问题（Low）
同上

## 五、规约符合性复核（条文比对）
两个协议各自的核查表（参考 §3.2 的表格模板）

## 六、测试覆盖与盲区分析
现有测试 + 盲区标记 + 导致漏报的原因

## 七、需求文档对照
project.md 功能矩阵逐行核实

## 八、历史审计对比
上一轮 vs 本轮的关键发现对比

## 九、附录：缺陷汇总表
表格：编号 | 严重度 | 文件:行 | 简述 | 新增/沿用/复发
```

### 4.3 缺陷严重度分级

| 级别 | 标记 | 定义 | 示例 |
|------|------|------|------|
| **Critical** | C | 核心功能不可用、数据完整性彻底破坏、系统崩溃 | 模拟器引擎 `AttributeError` |
| **Medium** | M | 功能行为偏离规约、静默数据错误但不崩溃、误导性文档 | 充值量字节序反、小时报静默丢数据 |
| **Low** | L | 死代码、文档不一致、弱断言测试、格式化问题 | 死代码、伪测试无 assert |

### 4.4 关键写作原则

1. **必须附带实际验证结果**：不能只说"代码看起来正确"，必须贴运行输出或断言结果
2. **必须追溯漏报原因**：每条新增缺陷需要分析为什么前几轮审计没发现
3. **必须引用规约原文**：每条缺陷标注规约章节号/表号
4. **禁止"大概""可能"等模糊措辞**：必须用 `✅`/`❌`/`⚠️` 明确标记
5. **缺陷编号规则**：`C-1, C-2 / M-1, M-2 / L-1, L-2`，跨轮次不复用

---

## 五、常见审计盲区（历史教训）

以下区域过去 8 轮审计中**最容易漏检**，每轮必查：

| 盲区 | 漏检轮次 | 教训 |
|------|----------|------|
| **模拟器引擎运行路径** | v1.1~v1.7（7 轮） | 测试覆盖 0 处，必须实际执行 `add_station` |
| **编码器数据域值正确性** | v1.1~v1.7 | 测试仅校验 CRC+AFN，不校验数据值。必须编→解→验值 |
| **小时报编码** | v1.1~v1.7 | 无任何测试调用。必须构造 12 组 + 非 12 组两路验证 |
| **SL427 下行参数设置往返** | v1.1~v1.7 | 解码器不解析下行参数设置帧，无法形成往返校验 |
| **伪测试无断言** | v1.1~v1.7 | `test_invalid_bcd_graceful` 恒通过。必须检查每个测试函数的 assert 语句 |
| **字节序（大端/小端）** | v1.7~v1.8 | SL427 数据域统一小端（规约表13/14/34等），但不同编码器方法可能不一致 |
| **定义符与实际数据长度不匹配** | v1.8 | 定义符声明 24B 但循环按输入长度写，CRC 自洽掩盖错误 |
| **文档声明的修复未落实** | v1.7→v1.8 | v1.7 L-3 声称修了测试计数但实际未修。不信任报告自我声明 |

---

## 六、审计工作流

### 6.1 单轮审计 SOP

```bash
# ============================================================
# 首次审计 (v1.X 第一轮) — 一次性建立基线认知
# ============================================================
# 以下 2 个规范文件只需在接手时通读一次，后续轮次无需重复：
 阅读 行业规范/水文监测数据通信规约SL651-2014.txt     # ~8000行，附录A/B/C/D/E为重点
 阅读 行业规范/水资源监测数据传输规约SL427-2021.txt    # ~2700行，§6.3/§7为重点

# ============================================================
# 每轮审计 SOP
# ============================================================

# 1. 读取本轮基线（每次必读）
阅读 docs/project.md          # 确认需求基线（关注 Roadmap 变更）
阅读 docs/handoff_main.md          # 确认最新能力清单与 TODO
阅读 audit/audit_report_v1.N.md    # 上一轮审计报告（重点：缺陷列表+盲区分析）

# 2. Layer 1：规约比对
# 首次审计：逐行比对全量常量表
# 后续轮次：仅检查当前轮次变更的代码（git diff 定位），核实变更未偏离规约
对比 sl651/constants.py ↔ 行业规范附录（首次全量，后续增量）
对比 sl427/constants.py ↔ SL427 规约正文
对比 crc.py / bcd.py ↔ 算法章节

# 3. Layer 2：需求对照
逐行核对 project.md 功能矩阵

# 4. Layer 3：构造性回放（必须实际执行）
python tests/test_sl651.py                                    # 全部通过？
python tools/decode_cli.py sl651 --file examples/fujian_messages.txt  # 0 失败？
python tools/decode_cli.py sl651 --file examples/beijing_messages.txt  # 0 失败？

# 编码器值验证（Python 交互式）
python -c "
# 对每个编码器方法：编→解→验值（不仅仅是 CRC）
"

# 模拟器引擎入口验证
python -c "
from simulator.engine import SimulatorEngine
from simulator import MqttxSender, WaterLevelStation
# add_station 不崩
"

# 5. Layer 4：历史缺陷复核
逐条检查上轮缺陷修复状态

# 6. 写报告
写入 audit/audit_report_v1.X.md（X=N+1）
```

### 6.2 每轮必须检查的代码位置

```
sl651/constants.py        ← 常量表是否与规约附录完全一致
sl651/crc.py              ← CRC16 验证向量
sl651/bcd.py              ← BCD 编解码往返
sl651/decoder.py          ← decode() + _parse_elements + _parse_ascii_elements + _parse_status
sl651/encoder.py          ← 每个 build_* 方法
sl427/constants.py        ← AFN_MAP / CTRL_FUNC_MAP / ALARM_BITS / TERMINAL_BITS / COMP_BITS
sl427/decoder.py          ← decode() + _parse_ctrl_func_data + _parse_comprehensive + _format_addr
sl427/encoder.py          ← 每个 build_* 方法（特别注意字节序）
simulator/engine.py       ← add_station() 入口
simulator/water_level_station.py ← generate_elements + check_alert_trigger
simulator/rain_station.py ← generate_elements + is_raining
simulator/sender.py       ← MqttxSender / TcpSender
tools/decode_cli.py       ← 双协议 CLI
tools/simulate_cli.py     ← 模拟器 CLI 入口
web/app.py                ← Flask 解码界面入口
tests/test_sl651.py       ← 每个测试函数是否有有效 assert
requirements.txt          ← 依赖声明完整性
```

---

## 七、快速上手命令

```bash
# 验证当前基线
cd /Users/wainshine/Workman/SL651/sl651-toolkit
python3 tests/test_sl651.py                          # 57 项测试
python3 tools/decode_cli.py sl651 --file examples/fujian_messages.txt  # 23 条
python3 tools/decode_cli.py sl651 --file examples/beijing_messages.txt  # 25 条

# 启动 Web 界面（验证可用）
python3 web/app.py                                    # → http://localhost:5050

# 模拟器冒烟（验证引擎不崩）
python3 -c "
from simulator import WaterLevelStation, MqttxSender
from simulator.engine import SimulatorEngine
engine = SimulatorEngine(MqttxSender('127.0.0.1', 1883))
engine.add_station(WaterLevelStation('1234567890', base_level=5.0))
print('OK')
"
```

---

## 八、交接清单

| 给谁 | 内容 |
|------|------|
| 下一任审计 | 本文档 + `audit/audit_report_v2.3.md`（最新） |
| 开发 | 审计报告 v1.8 中的缺陷列表（供修复参考） |
| 测试 | 审计报告 v1.8 §六 盲区分析（供补充测试） |

---

## 九、我的评估

1. **审计方法论已迭代成熟**：从 v1.1~v1.5 的纯静态阅读（大量漏报），到 v1.7 加入部分回放（仍漏报模拟器），到 v1.8 加入四层模型全覆盖（发现 C-1/M-1/M-2 三个关键盲区缺陷）。下一任应严格遵循 Layer 1~4 流程。
2. **最大教训**："测试通过 ≠ 行为正确"。CRC 自洽会掩盖数据正确性问题；伪测试会掩盖真实缺陷。必须实际执行、构造边界用例、校验数据值。
3. **核心算法已稳定**：CRC16/MODBUS、CRC8(0xE5)、定义符解析、负数BCD、SL651帧结构、SL427控制域/地址域/Tp 经 8 轮比对+真实报文验证，可信度高，后续轮次可降低检查频率。
4. **建议下一轮优先关注**：模拟器加报机制端到端、SL427 81/82/84 编码往返、小时报编码往返、CLI 集成测试。
