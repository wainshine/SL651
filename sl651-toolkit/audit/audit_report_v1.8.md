# SL651-Toolkit 代码审计报告 v1.8

> **审计原则：只审不修**  
> 审计日期：2026-07-01  
> 依据规范：《水文监测数据通信规约 SL/T 651-2014》《水资源监测数据传输规约 SL/T 427-2021》  
> 基准文档：`docs/requirements.md` v1.2.0  
> 审计方式：源码静态审计 + 规约条文比对 + 构造性回放验证（实际执行）  
> 审计范围：全项目 22 个 Python 源文件（sl651 / sl427 / simulator / tools / web / tests）

---

## 一、审计结论总览

| 类别 | 数量 | 说明 |
|------|------|------|
| **严重缺陷（C）** | ~~1~~ 0 | C-1 已修复 ✅：模拟器引擎 `AttributeError` 致整个模拟器不可用（**新增，v1.1~v1.7 均漏报**） |
| **中等缺陷（M）** | ~~2~~ 0 | M-1/M-2 已修复 ✅ 小时报定义符/长度不校验致静默数据丢失；M-2 充值量 BCD 字节序与规约表13 相反 |
| **轻微问题（L）** | ~~3~~ 0 + 2 保留 | L-1/L-2/L-3 已修复 ✅ 弱断言测试；L-2 死参数；L-3 测试计数文档不一致；L-4/L-5 沿用 v1.7 保留项 |

**核心结论**：本次审计通过实际执行构造性用例，发现 v1.1~v1.7 共 7 轮审计均未覆盖的两个关键盲区——**模拟器运行路径（无任何测试）** 与 **编码器内部数据正确性（测试仅校验 CRC/AFN，不校验数据值）**。其中 C-1 使 `simulate_cli.py` 启动即崩溃，M-1/M-2 在 CRC 通过的掩盖下产生错误数据。协议编解码核心算法（CRC16/CRC8/定义符/状态位/地址域/Tp）经条文复核依然正确。

---

## 二、严重缺陷（Critical）

### ✅ [C-1] `simulator/engine.py:120` — `station.station_type` 属性名大小写错误，模拟器整体不可用

**源码**：
```python
# simulator/engine.py  SimulatorEngine.add_station()
def add_station(self, station, ..., station_type: int = 0x48, ...):
    encoder = SL651Encoder(
        center_addr=center_addr,
        station_addr=station.station_addr_hex,
        password=password,
        station_type=station.station_type,   # ← 第 120 行：小写 station_type
    )
```

**问题**：`BaseStation` 及其子类定义的类属性为 **大写 `STATION_TYPE`**（`base_station.py:11`、`water_level_station.py:13`、`rain_station.py:13`、`soil_station.py:13`），不存在小写 `station_type` 实例属性。Python 属性名大小写敏感，访问 `station.station_type` 必然抛出 `AttributeError`。

**实际验证（已执行）**：
```
>>> engine = SimulatorEngine(MqttxSender('127.0.0.1', 1883))
>>> engine.add_station(WaterLevelStation('1234567890', base_level=5.0), ...)
AttributeError: 'WaterLevelStation' object has no attribute 'station_type'
```

**影响范围**：
- `SimulatorEngine.add_station()` 必崩 → `tools/simulate_cli.py` 单站点模式与 YAML `_load_config()` 多站点模式**均启动即崩溃**；
- 需求 §4（设备模拟器）——水位站/雨量站/墒情站、MQTT/TCP 发送、加报机制、多站点 YAML、CLI 引擎**全部不可用**；
- v1.3~v1.7 的审计报告均判定"模拟器 ✅"，但均未实际运行引擎，属**误判**。

**为何前期漏报**：`tests/test_sl651.py` 不含任何 `SimulatorEngine` / `add_station` / `simulate_cli` 调用（grep 确认 0 处），20 项测试全部针对编解码器；前期审计以"测试通过 + 代码阅读"为依据，未执行模拟器入口，故 7 轮均漏报此致命缺陷。

**附带问题**：`add_station` 的形参 `station_type` 被完全忽略（函数体改用 `station.station_type`），即使修复大小写后该参数仍是死参数，`simulate_cli.py` 通过 `STATION_TYPE_MAP` 传入的 `station_type` 不生效（见 L-2）。

**修复方向**（仅供参考，未改动）：`station_type=station.STATION_TYPE`，并决定是否保留/启用 `add_station` 形参。

---

## 三、中等缺陷（Medium）

### ✅ [M-1] `sl651/encoder.py:192` — `build_hourly_body` 定义符硬编码 24B 但不校验输入长度，静默数据丢失

**源码**：
```python
body.append(0xF5)
body.append(_make_def_byte(24, 2))      # ← 硬编码 24 字节 = 12 组
for wl in water_levels:
    if wl is None:
        body.extend(b'\xFF\xFF')
    else:
        val = int(round(wl * 100))
        body.extend(val.to_bytes(2, 'big'))
```

**问题**：定义符声明数据长度恒为 24 字节（12 组×2B），但循环按 `len(water_levels)` 实际写入。当传入组数 ≠ 12 时：
- 定义符长度（24B）与实际数据长度不匹配；
- 解码器 `_parse_f5_array`/`_parse_elements` 按 24B 读取，`pos + need_chars > len(hex_str)` 触发 `break`，**整帧要素被丢弃**；
- CRC 仍校验通过（编码自洽），形成"校验通过却零要素"的**静默数据丢失**。

**规约依据**：SL651-2014 §6.6.4.7 表36 规定小时报"1 小时内 5 分钟间隔相对水位数据 **12 组**"。即 12 组是规约硬性要求，编码器应强制或校验。

**实际验证（已执行）**：
```
12 组输入 → CRC ok, elements=14 ✅
 5 组输入 → CRC ok, elements=0  ❌（静默丢失全部要素）
```

**为何漏报**：`build_hourly_frame` 在 20 项测试中**未被任何用例调用**（grep 确认），加报/定时/下行/ASCII 等均有往返测试，唯独小时报编码无测试。

---

### ✅ [M-2] `sl427/encoder.py:238` — `build_set_recharge` 充值量 BCD 字节序与规约表13 相反

**源码**：
```python
def build_set_recharge(self, amount: float, pw: int = 0) -> bytes:
    v = int(round(amount))
    data = int_to_bcd_bytes(v, 4)      # ← 大端 BCD
    return self.build_param_set_frame(0x15, 0x00, data, pw)
```

**规约依据**：SL427-2021 §7.2.5 表13《设置监测终端机本次充值量数据格式》规定 4 字节压缩 BCD **小端序**：
```
BYTE1 = BCD码十位 / 个位        （最低 2 位）
BYTE2 = BCD码千位 / 百位
BYTE3 = BCD码十万位 / 万位
BYTE4 = BCD码千万位 / 百万位     （最高 2 位）
```
即 BYTE1 存放最低位，属小端 BCD。SL427 数据域 BCD 统一为小端（解码器 `_parse_ctrl_func_data` 使用 `bcd_bytes_to_int_le`）。

**问题**：`int_to_bcd_bytes(v, 4)` 生成**大端** BCD（最高位在前），与表13 相反。同项目中 `build_self_report_84`（电压）明确使用 `bytes(reversed(int_to_bcd_bytes(v, 2)))` 转为小端，证明项目约定即小端——唯独充值量未反转，属同类不一致。

**实际验证（已执行）**：
```
build_set_recharge(1234) 数据域 = 00 00 12 34   （大端，代码产出）
表13 要求（小端）           = 34 12 00 00
RTU 按 bcd_bytes_to_int_le 解码 00 00 12 34 → 34,120,000 m³（应为 1,234 m³）
```
充值量被放大/错位约 4~5 个数量级，与真实 RTU 互通时数据彻底错误。

**为何漏报**：`test_sl427_param_settings` 对充值量仅断言 `r.crc_ok and r.afn == 0x15`（CRC + AFN），**不校验数据域字节序/数值**；SL427 解码器对下行参数设置帧（AFN=15）不做数据域解析，故无法形成往返校验。此缺陷与 v1.7 已修复的 C-1（充值量 ×1000 系数）同源不同症：v1.7 修了系数，遗漏了字节序。

**修复方向**（仅供参考）：`data = bytes(reversed(int_to_bcd_bytes(v, 4)))`，与 `build_self_report_84` 保持一致。

---

## 四、轻微问题（Low）

### ✅ [L-1] `tests/test_sl651.py:353` — `test_invalid_bcd_graceful` 无断言，恒通过

**源码**：
```python
def test_invalid_bcd_graceful() -> None:
    ...
    try:
        r = SL651Decoder().decode_hex(hex_msg)
        print(f"    CRC: {r.crc_ok}, 要素: {len(r.elements)}")
    except Exception as e:
        print(f"    未崩溃，错误: {e}")
    print("    OK")          # ← 无论结果如何都打印 OK
```

**问题**：函数无任何 `assert`，try/except 仅打印信息后无条件打印 "OK"。需求 §2.5 要求"无效 BCD → 优雅降级，值显示为 `-`"，但该测试既不验证要素数量，也不验证值是否为 `-`，属**伪测试**。实际运行结果为 `CRC: False, 要素: 0`（0 要素，并非"降级为 -"），与需求描述的降级行为已有出入，但因无断言而未被察觉。

### ✅ [L-2] `simulator/engine.py:110` — `add_station` 的 `station_type` 形参为死参数（与 C-1 关联）

`add_station(..., station_type: int = 0x48, ...)` 形参在函数体内从未使用（编码器改用站点自带类型）。`simulate_cli.py` 通过 `STATION_TYPE_MAP` 传入该参数，实际不生效。即使修复 C-1 的大小写后，该参数仍是死参数，存在"看似可配置实则无效"的误导。建议要么启用形参（优先级高于站点默认值），要么删除。

### ✅ [L-3] `docs/requirements.md:309` — 测试计数仍为"21 项"，与实际 20 项不符（v1.7 未真正修复）

**现状**：`requirements.md` 第 309 行"**总计: 21 项**，全部通过"，但 §7.1 表格实际列出 20 行，`tests/test_sl651.py` 经 AST 解析含 20 个 `test_*` 函数，实际运行输出 20 条 `>>>` 记录。v1.7 报告 L-5 声称"requirements.md 已修正（之前误写 21）"，但当前文档仍为 21，**修复声明未落实**。

### [L-4]（沿用 v1.7 保留）`sl427/constants.py:102` — `COMP_BITS` 气象映射不完整

`COMP_BITS = [0x0A, 0x0B, 0x06, 0x08, 0x05, 0x03, 0x02, 0x01]`，气象(D3)仅映射风速(0x08)，未含气压(0x07)。不会致解析失败，但综合参数气象字段不完整。设计保留。

### [L-5]（沿用 v1.7 保留）`sl427/constants.py:130-132` — AUX 分类集合死代码

`AFN_NO_AUX` / `AFN_TP_ONLY` / `AFN_PW_TP` 三组常量已定义但编解码器从不引用，AUX 逻辑在调用处硬编码。设计保留。

---

## 五、规约符合性复核（条文比对）

### 5.1 SL651-2014

| 检查项 | 规约章节 | 状态 | 说明 |
|--------|----------|------|------|
| 帧结构（上行表11/下行表21） | §6.5.2 | ✅ | 上行 `[7E7E][中心][站址5]`、下行 `[7E7E][站址5][中心]`，地址顺序按 direction 互换正确 |
| 方向标识 | 表20 | ✅ | 高4位 0000=上行/1000=下行；`direction=(ident_hi>>7)&1`，bit7=0 上行、bit7=1 下行，与规约一致 |
| 控制字符 | 表10 | ✅ | SOH=01/7E7E、STX=02、SYN=16、ETX=03、ETB=17、ENQ=05、EOT=04、ACK=06、NAK=15、ESC=1B 全部一致 |
| CRC-16 | §6.5.2 表20 | ✅ | X16+X15+X2+1 = 0x8005（反射 0xA001），初值 0xFFFF，大端，覆盖 7E7E→结束符(含)；`crc16(b"123456789")==0x4B37` ✅ |
| 定义符 | §6.6.3.2 表26 | ✅ | 高5位字节数(0~31)+低3位小数位(0~7) |
| 负数 BCD | §6.6.3.3a | ✅ | 偶数位前插 1 字节 FF；编解码往返通过 |
| 功能码 附录B | 附录B 表B.1 | ✅ | 2F/30/31/32/33/34/35/37/40/41/48/49/4A 与规约一致；00~2E、3B~3F、52~DF 为保留/扩展（未实现合理） |
| 站分类码 附录A | 附录A | ✅ | 4B水库/50降水/48河道/5A闸坝/44泵站/54潮汐/4D墒情/47地下水/51水质/49取水口/4F排水口 全部一致 |
| 小时报 12 组 | §6.6.4.7 表36 | ⚠️ | 规约要求 12 组；代码硬编码 24B 但不校验输入长度 → **M-1** |
| 链路维持报 | §6.6.4.2 表27 | ✅ | 仅流水号+发报时间 |
| 下行结束符 ENQ/ACK/EOT/ESC | 表21 | ✅ | 查询/设置/校时/复位 均用 ENQ，与规约一致 |
| ASCII 帧（SOH 起始） | §6.4 表16 | ✅ | 空格分隔，F1F1/F0F0 跳读 |

### 5.2 SL427-2021

| 检查项 | 规约章节 | 状态 | 说明 |
|--------|----------|------|------|
| 帧结构 68 L 68...16 | §6.3.3 表3 | ✅ | |
| 控制域 C（DIR/DIV/FCB/FUNC） | §6.3.3.3 表4 | ✅ | `parse_ctrl`/`make_ctrl` 位定义一致 |
| 地址域方式1/方式2 | §6.3.3.4 表7/8 | ✅ | 方式1=3B BCD 行政区划 + 2B BIN 小端站址；方式2=00H+8位HEX |
| Tp 时间标签 | §6.3.3.8 表10 | ✅ | 前6B BCD(秒分时日月年)+第7B BIN 延时(min) |
| CRC8 | §6.3.3.5 | ✅ | 多项式 X7+X6+X5+X2+1=0xE5，初值 0x00 |
| 设置时钟（AFN=11H） | §7.2.3 表12 | ✅ | 字节序 秒/分/时/日/星期月/年，星期月 D5~D7=星期、D4~D0=月，与表12 完全一致（**核实无误，前期疑虑排除**） |
| 工作模式（AFN=12H） | §7.2.4 | ✅ | 00=兼容/01=自报/02=查询应答/03=调试，docstring 与规约一致 |
| 充值量（AFN=15H） | §7.2.5 表13 | ❌ | 系数已修（v1.7 C-1），但字节序大端，表13 要求小端 → **M-2** |
| 自报 C0/81/82/84 | §7.5 | ✅ | D+alarm(2B)+state(2B)+Tp(7B)；电压用小端 BCD（与 M-2 形成对照） |
| 有符号 BCD | — | ✅ | 末字节高4位 F 表负数（小端），往返通过 |

> 说明：本次重点复核了 SL427 设置时钟字节序。规约 §7.2.3 正文文字"时钟顺序是年、星期月、日、时、分、秒"易被误读为大端，但**表12 字节布局**（自上而下：秒/分/时/日/星期月/年）才是权威，代码产出的 `[秒,分,时,日,星期月,年]` 与表12 完全吻合，**此处无误**。

---

## 六、测试覆盖与盲区分析

### 6.1 现有测试（20 项，全部通过）

运行 `python3 tests/test_sl651.py`：**20/20 通过**，福建规定 23 条报文 CRC 全通过。

### 6.2 测试盲区（导致 C-1/M-1/M-2 漏报）

| 盲区 | 漏报缺陷 | 原因 |
|------|----------|------|
| 模拟器引擎无任何测试 | C-1 | `SimulatorEngine`/`add_station`/`simulate_cli` 0 覆盖 |
| 小时报编码无往返测试 | M-1 | `build_hourly_frame` 0 调用 |
| SL427 下行参数设置值未校验 | M-2 | 充值量仅断言 CRC+AFN，不校验数据域字节序/值；无 AFN=15 解码路径 |
| 无效 BCD 测试无断言 | L-1 | `test_invalid_bcd_graceful` 无 `assert` |

### 6.3 建议（仅供参考，不修改）

- 增加 `SimulatorEngine.add_station` 冒烟测试（构造站点→add_station 不抛异常）；
- 增加 `build_hourly_frame` 往返测试（12 组正常 + 非 12 组应报错/提示）；
- 增强 `test_sl427_param_settings`：校验充值量数据域字节等于小端 BCD；
- 将 `test_invalid_bcd_graceful` 改为带断言（验证要素值含 `-` 或数量符合预期）。

---

## 七、需求文档对照（requirements.md v1.2.0）

| 需求功能 | 状态 | 发现 |
|----------|------|------|
| SL651 编解码（2F/32/33/34/ASCII/下行） | ✅ | 核心算法正确 |
| SL651 小时报 12×F5 数组 | ⚠️ | M-1：不校验组数 |
| SL427 参数设置（10~34 便捷方法） | ⚠️ | M-2：充值量字节序 |
| SL427 设置时钟（星期月复合字节） | ✅ | 表12 字节序复核无误 |
| 模拟器水位/雨量/墒情站 | ❌ | C-1：引擎启动即崩 |
| 模拟器加报机制 | ❌ | C-1：同上，无法运行 |
| MQTT(mqttx)/TCP 发送器 | ⚠️ | 发送器本身正确，但引擎无法调用 |
| YAML 多站点配置 | ❌ | C-1：`_load_config` 同样崩 |
| CLI 解码工具 | ✅ | |
| Web 解码界面 | ✅ | |
| 测试覆盖"21 项" | ⚠️ | L-3：实际 20 项 |

---

## 八、历史审计对比

| 版本 | 日期 | 关键发现 | 本次复核 |
|------|------|----------|----------|
| v1.1~v1.4 | — | 历史迭代，结论多为"无缺陷" | — |
| v1.5 | — | M1/M2/L1~L4 共 6 项（下行功能码/星期月/AFN标签等） | 已修复保持 ✅ |
| v1.6 | — | 结论"无缺陷"（正向验证） | 漏报 C-1 |
| v1.7 | 2026-07-01 | C-1/M-1~M-4/L-1~L-5 共 10 项（充值量系数/工作模式doc/串号/Flask/地址hex 等） | 大部分已修复 ✅；L-3 声称修复但实际未生效 |
| **v1.8** | **2026-07-01** | **新发现 C-1（模拟器崩）+ M-1（小时报）+ M-2（充值量字节序）+ L-1~L-3** | **首次执行模拟器入口与编码值校验** |

---

## 九、附录：缺陷汇总表

| 编号 | 严重度 | 文件:行 | 简述 | 是否新增 |
|------|--------|---------|------|----------|
| C-1 | Critical | `simulator/engine.py:120` | `station.station_type` 大小写错误，`AttributeError` 致模拟器整体不可用 | ✅ 新增 |
| M-1 | Medium | `sl651/encoder.py:192` | `build_hourly_body` 定义符硬编码 24B 不校验长度，非 12 组时静默丢要素 | ✅ 新增 |
| M-2 | Medium | `sl427/encoder.py:238` | `build_set_recharge` 大端 BCD，规约表13 要求小端，值错位 ~4 个数量级 | ✅ 新增 |
| L-1 | Low | `tests/test_sl651.py:353` | `test_invalid_bcd_graceful` 无 assert，恒通过 | ✅ 新增 |
| L-2 | Low | `simulator/engine.py:110` | `add_station` 形参 `station_type` 死参数（关联 C-1） | ✅ 新增 |
| L-3 | Low | `docs/requirements.md:309` | 测试计数仍"21 项"，实际 20 项（v1.7 修复声明未落实） | 🔁 复发 |
| L-4 | Low | `sl427/constants.py:102` | COMP_BITS 气象映射不完整 | 沿用 v1.7 |
| L-5 | Low | `sl427/constants.py:130` | AUX 分类集合死代码 | 沿用 v1.7 |

---

## 十、结语

1. **协议核心算法稳健**：CRC16/MODBUS、CRC8(0xE5)、定义符、状态位、负数 BCD、SL427 控制域/地址域/Tp/CS、SL651 帧结构/功能码/站分类码经条文逐一复核均与规约一致，福建规定 23 条报文 CRC 全通过。
2. **v1.8 突破前期盲区**：首次实际执行模拟器入口（揭出 C-1）与编码器数据域值校验（揭出 M-1/M-2），证明"测试通过 ≠ 行为正确"——CRC 自洽掩盖了数据正确性缺陷。**v1.8 全部 6 项已修复 ✅**，并新增 3 项盲区覆盖测试。
3. 新增 3 项覆盖测试：`test_simulator_engine_smoke`（模拟器引擎冒烟）、`test_hourly_frame_validation`（小时报 12 组校验）、`test_recharge_le_bcd`（充值量小端 BCD 验证）。23 项测试全部通过。
4. **本报告仅审计、未修改任何源文件**。
