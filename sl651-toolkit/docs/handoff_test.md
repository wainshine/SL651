# SL651-Toolkit 测试交接文档

> 角色：业务测试1代  
> 接棒时间：2026-07-01  
> 基线版本：v1.2.7  
> 接手前必读：`docs/project.md` + `README.md` + `docs/handoff_main.md` + 本文档

---

## 一、当前测试状态

### 1.1 一次性运行结果

```
53/53 项测试全部通过
福建 23 条真实报文 CRC + 要素级基线全通过
北京 25 条真实报文 CRC + 要素级基线全通过
```

```bash
python3 tests/test_sl651.py
# 输出末尾: "所有测试通过"
```

### 1.2 审计历史（已闭环）

| 轮次 | 审计报告 | 关键发现 | 本次验证 |
|------|----------|----------|----------|
| v1.1~v1.7 | `audit/audit_report_v1.*.md` | 累计 ~20 项缺陷全部修复 | 24 项测试通过 |
| **v1.8** | `audit/audit_report_v1.8.md` | **C-1: 模拟器引擎致命 bug (AttributeError)**, M-1: 小时报不校验, M-2: 充值量 BCD 字节序 | **v1.8 发现的全 6 项已修复** / 3 项盲区覆盖测试已新增 |
| **v2.2** | `audit/audit_report_v2.2.md` | **C-1: 0x31 均匀报丢失 11/12 组**, M-1: F5 定义符失配截断, M-4: 真实报文仅验 CRC | **v1.2.7 已全部修复**；真实报文增加要素级基线（52 项测试） |

### 1.3 缺陷跟踪表（v1.8 基准，已全闭环）

| 编号 | 严重度 | 文件:行 | 简述 | 状态 |
|------|--------|---------|------|------|
| C-1 | Critical | `simulator/engine.py:120` | `station.station_type` 大小写错误 → `AttributeError` | ✅ 已修复 (`station_type or station.STATION_TYPE`) |
| M-1 | Medium | `sl651/encoder.py:192` | 小时报定义符硬编码 24B，非 12 组静默丢要素 | ✅ 已修复（新增组数校验） |
| M-2 | Medium | `sl427/encoder.py:238` | 充值量 BCD 大端→应为小端 LE | ✅ 已修复（`bytes(reversed(...))`） |
| L-1 | Low | `tests/test_sl651.py:353` | `test_invalid_bcd_graceful` 无 assert | ✅ 已修复（加入 assert） |
| L-2 | Low | `simulator/engine.py:110` | `add_station` 形参 `station_type` 死参数 | ✅ 已修复 |
| L-3 | Low | `docs/project.md` §7.1 | 测试计数已同步为 **52 项**（v1.2.7） | ✅ 已同步 |

---

## 二、测试环境

### 2.1 基础设施

```bash
Python:   3.10+
依赖:     零（核心编解码器）, PyYAML>=6.0（YAML 多站点）, flask（Web 界面）
系统依赖: mqttx CLI（仅 MQTT 模拟器模式）
编辑工具: 任意
```

### 2.2 快速验证命令

```bash
# 1. 基础测试
python3 tests/test_sl651.py

# 2. 真实报文验证
python3 tools/decode_cli.py sl651 --file examples/fujian_messages.txt
python3 tools/decode_cli.py sl651 --file examples/beijing_messages.txt

# 3. 单条解码验证
python3 tools/decode_cli.py sl651 --hex "7E7E2500418D2337..."

# 4. Web 界面
python3 web/app.py   # 浏览器 http://localhost:5050
```

---

## 三、测试用例清单

### 3.1 `tests/test_sl651.py` 24 项全览（v1.1 基线快照；最新 53 项清单见 `docs/project.md` §7.1）

| 序号 | 测试函数 | 协议 | 覆盖点 | 类型 |
|------|----------|------|--------|------|
| 1 | `test_bcd` | 通用 | BCD 编解码往返、时间 BCD ± | 单元 |
| 2 | `test_crc` | 通用 | CRC-16/MODBUS 验证向量 (0x4B37) | 单元 |
| 3 | `test_def_byte` | SL651 | 定义符解析 (0x23→(4,3)) | 单元 |
| 4 | `test_decode_njnrs` | SL651 | njnrs 示例定时报（CRC + 5要素 + 站类） | 集成 |
| 5 | `test_decode_watertester` | SL651 | 水测家加报报（含 FF 子标识符 + 状态位） | 集成 |
| 6 | `test_encode_decode_roundtrip` | SL651 | 编码→解码往返（定时报 2要素） | 集成 |
| 7 | `test_crc8` | SL427 | CRC8 验证向量 | 单元 |
| 8 | `test_sl427_decode` | SL427 | njnrs C0 帧解码（AFN+CRC+功能码名称） | 集成 |
| 9 | `test_sl427_encoder_roundtrip` | SL427 | heartbeat + C0 往返 | 集成 |
| 10 | `test_sl427_address_encoding` | SL427 | 方式1 BCD+BIN、方式2 8位HEX、异常输入 | 单元 |
| 11 | `test_sl427_tp_encoding` | SL427 | Tp 7B 各字段（秒/分/时/日/月/年/延时） | 单元 |
| 12 | `test_sl427_c0_signed_value` | SL427 | 有符号水位负数往返 | 集成 |
| 13 | `test_sl427_invalid_l` | SL427 | 畸形 L 长度 → DecodeError | 异常 |
| 14 | `test_sl427_downlink` | SL427 | 下行帧解码（DIR=0 确认帧 + 查询响应） | 集成 |
| 15 | `test_sl651_downlink_frames` | SL651 | 查询/设置/校时/复位下行帧 + ETX/ENQ 验证 | 集成 |
| 16 | `test_sl427_param_settings` | SL427 | 设置地址/时钟/充值/IC卡往返 | 集成 |
| 17 | `test_sl651_ascii` | SL651 | ASCII 编解码（SOH 起始，Z/Q/VT 标识符） | 集成 |
| 18 | `test_fujian_messages` | SL651 | **23 条福建规定报文 CRC 全验证**（14种功能码） | 回归 |
| 19 | `test_simulator_engine_smoke` | 模拟器 | 引擎 add_station 不崩 + 编码帧 CRC 通过 | 冒烟 |
| 20 | `test_hourly_frame_validation` | SL651 | 小时报非 12 组应报 EncodeError / 12组正常生成 | 异常 |
| 21 | `test_recharge_le_bcd` | SL427 | 充值量小端 BCD 字节序验证 (1234→34120000) | 单元 |
| 22 | `test_beijing_messages` | SL651 | **25 条北京水务报文 CRC 全验证** | 回归 |
| 23 | `test_negative_bcd` | SL651 | 负数 BCD（0xFF 前缀）往返 (-0.345 水位) | 集成 |
| 24 | `test_invalid_bcd_graceful` | SL651 | 畸形 BCD 帧不崩溃/CRC 不通过 | 异常 |

---

## 四、测试覆盖分析

### 4.1 协议功能码覆盖（SL651）

| 功能码 | 报文类型 | 解码测试 | 编码测试 | 往返测试 | 状态 |
|--------|----------|----------|----------|----------|------|
| 0x2F | 链路维持报 | ✅ (福建) | ✅ | — | |
| 0x31 | 均匀报 | ✅ (福建 F4/F5) | — | — | |
| 0x32 | 定时报 | ✅ (njnrs/福建/北京) | ✅ | ✅ | |
| 0x33 | 加报报 | ✅ (水测家/北京) | ✅ | ✅ | |
| 0x34 | 小时报 | ✅ (福建/北京) | ✅ (12组) | ❌ **无往返** | ⚠️ |
| 0x35 | 人工置数报 | ✅ (福建) | — | — | |
| 0x37 | 查询实时数据 | ✅ (福建下行) | ✅ | ✅ | |
| 0x40 | 修改基本配置 | ✅ (福建下行) | ✅ | ✅ | |
| 0x41 | 读取基本配置 | ✅ (福建) | — | — | |
| 0x48 | 恢复出厂设置 | ✅ (福建下行) | ✅ | ✅ | |
| 0x49 | 修改密码 | ✅ (福建) | — | — | |
| 0x4A | 设置时钟 | ✅ (福建下行) | ✅ | ✅ | |

### 4.2 SL427 AFN 覆盖

| AFN | 解码 | 编码 | 往返 | 异常 |
|-----|------|------|------|------|
| 02 (心跳) | ✅ | ✅ | ✅ | ✅ (畸形L) |
| C0 (自报实时) | ✅ | ✅ | ✅ | |
| 81 (自报告警) | ✅ | ✅ | — | |
| 82 (人工置数) | ✅ | ✅ | — | |
| 83 (图片) | ✅ | — | — | |
| 84 (电压) | ✅ | ✅ | — | |
| B0 (查询/响应) | ✅ | ✅ | ✅ | |
| 61 (查询图像) | ✅ | — | — | |
| 10 (设置地址) | — | ✅ | ✅ | |
| 11 (设置时钟) | — | ✅ | ✅ | |
| 12 (工作模式) | — | ✅ | — | ❌ |
| 15 (充值量) | — | ✅ | ✅（含字节序） | |
| 30/31 (IC卡) | — | ✅ | ✅ | |

### 4.3 盲区标记

| 盲区 | 风险 | 优先级 |
|------|------|--------|
| **小时报编码往返测试缺失** | M-1 同类问题可能复现；当前仅有组数校验，无完整编解码往返 | **P1** |
| **SL427 工作模式编码往返缺失** | `build_set_work_mode` 无测试 | P2 |
| **模拟器端到端测试缺失** | MQTT/TCP broker 联调未验证，仅冒烟测试 | P2 |
| **模拟器加报机制测试缺失** | 雨量站 `is_raining` / 水位站 `check_alert_trigger` 无验证 | P2 |
| **F4/F5 均匀报数组编码无测试** | 仅解码有测试，编码无 | P2 |
| **SL427 81/82/84 编码往返缺失** | 有编码器方法但无往返测试 | P3 |
| **CLI 工具集成测试缺失** | `decode_cli` / `simulate_cli` 无自动化测试，依赖人工 | P3 |
| **Web 界面测试缺失** | Flask 无自动化测试 | P3 |

---

## 五、接手后的测试计划（建议）

### 5.1 第一优先级：填补盲区回归测试

1. **小时报编解码往返**：`build_hourly_frame(12组水位) → decode → 验证 CRC + 14 要素**
2. **小时报非 12 组异常**：5组/13组 → 应抛 EncodeError（已有20，需补充 13组、0组）

### 5.2 第二优先级：增强现有测试

3. **充值量数值验证**：不止验证 CRC+AFN，还需验证解码后的价格数值 = 原始输入
4. **模拟器引擎完整路径**：`add_station → runner 生成帧 → decode → 验证要素值对应**
5. **加报触发逻辑**：雨量站设置 `raining=True`，水位站设置水位变化超过阈值

### 5.3 第三优先级：端到端联调

6. **TCP 联调**：启动 `nc -l 5001` → 运行 `simulate_cli --proto sl651` → 验证收到的 hex 可解码
7. **MQTT 联调**：启动 mosquitto → 运行 `simulate_cli --proto mqtt` → 验证 mqttx publish

---

## 六、测试数据文件

| 文件 | 条数 | 协议 | 说明 |
|------|------|------|------|
| `examples/sample_messages.txt` | 2 | SL651 | njnrs + 水测家示例 |
| `examples/fujian_messages.txt` | 23 | SL651 | 福建规定（14种功能码，CRC验证） |
| `examples/beijing_messages.txt` | 25 | SL651 | 北京水务（8测站/3类报文，CRC验证） |
| `examples/stations.yaml` | — | 模拟器 | YAML 多站点配置示例 |
| `examples/mqttx_subscribe.txt` | — | 模拟器 | MQTTX 订阅参考 |

---

## 七、测试不变量（接手后不应退化）

| 条件 | 预期 | 验证方式 |
|------|------|----------|
| 53 项测试 | 全部通过 | `python3 tests/test_sl651.py` |
| 福建 23 条 | CRC 100% + 要素级基线 | `python3 tools/decode_cli.py sl651 --file examples/fujian_messages.txt` |
| 北京 25 条 | CRC 100% + 要素级基线 | `python3 tools/decode_cli.py sl651 --file examples/beijing_messages.txt` |
| CRC16 验证向量 | `crc16(b"123456789") == 0x4B37` | test_crc |
| CRC8 验证向量 | `crc8(b"\x00\x01\x02") == 0xA6` | test_crc8 |
| 定义符解析 | `parse_def_byte(0x23) == (4,3)` | test_def_byte |

---

## 八、已知遗留问题（不修项）

| 编号 | 位置 | 内容 | 影响评估 |
|------|------|------|----------|
| P1-TODO | `sl427/constants.py:98` | 0x0D 在多上下文含义不同（下行=报警, 上行=雨量, AFN=84H=电压），标签不统一 | 不影响编解码，仅标签歧义 |
| P2-远期 | `sl427/constants.py:130` | AFN_NO_AUX/AFN_TP_ONLY/AFN_PW_TP 三组常量已定义但无人引用 | 无影响 |
| P2-远期 | `sl427/constants.py:106` | COMP_BITS[3]=0x07 表示气象（含气压），非风速；v1.9 M-7 已修正 | 不影响解析 |
| P2-远期 | Roadmap | 多包 (SYN/ETB) 拼接重组 | 当前可解码单帧多包 |
| P2-远期 | Roadmap | SL427 参数设置全量 AFN (~30个变长格式) | 当前通用模板+6便捷方法 |
| L-3 | `docs/project.md` §7.1 | 测试计数已同步为 52 项（v1.2.7） | 已解决 |

---

## 九、测试交接清单

| 事项 | 给谁 | 说明 |
|------|------|------|
| 本文档 | 下一任测试 | 测试现状、盲区、计划 |
| `audit/audit_report_v1.8.md` | 下一任测试 | 最新审计结论 |
| `docs/project.md` | 全局 | 需求基线（注意 §7.1 计数需同步） |
| `docs/handoff_main.md` | 全局 | 开发侧交接 |

---

## 十、业务测试1代 — 实测发现

> 测试时间：2026-07-01 | 测试范围：BLT1~BLT10（盲区+源码审计） | 测试脚本：`tests/test_round1_blindspots.py`

### 10.1 缺陷清单

| 编号 | 严重度 | 文件:行 | 简述 | 详细 |
|------|--------|---------|------|------|
| **D-1** | **Medium** | `sl427/decoder.py:382` | **AFN=0x81/0x82/0x84 不解码 alarm/state/Tp** | AFN=C0 正确拆分 data_field 为 real_data + alarm(2B) + state(2B) + Tp(7B)，解出 21 个要素；而 81/82/84 走同一分支，将整个 data_field 直接丢给 `_parse_ctrl_func_data`，仅解析首 2B 电压，alarm/state/Tp 全部丢失。AFN=84 的 alarm/state 恒为 0 影响较小，但 Tp 丢失；81/82 的 alarm/state 可能非零 |
| **D-2** | **Low** | `sl651/encoder.py:200` | **小时报F5水位不支持负数** | `build_hourly_body` 的 F5 数组直接 `int(round(wl * 100)).to_bytes(2, 'big')`，不走 `_encode_bcd` 的 0xFF 负数前缀机制。输入负数水位 → `OverflowError: can't convert negative int to unsigned` |
| **D-3** | **Low** | `sl651/decoder.py:438` | **BCD元素value为字符串而非数值** | `_safe_bcd_val` 返回 `f"{r:.{decimals}f}"`（格式化字符串），但 ASCII 元素返回 float/int。API 用户无法用 `e.value * 2` 做数值运算（会变成字符串重复）。`test_encode_decode_roundtrip` 未校验值类型 |

### 10.2 盲区测试结果（10项全部执行）

| 测试项 | 结果 | 发现 |
|--------|------|------|
| 小时报12组往返 | ✅ | F5 12组+瞬时水位+电压均正确解码 |
| 小时报极端值（全零/负数） | ⚠️ | 全零通过；负数水位抛 OverflowError → **D-2** |
| 小时报非12组校验（0/1/5/11/13/24） | ✅ | 全部正确抛 EncodeError |
| SL427 AFN=0x81往返 | ✅ | CRC通过, 仅3要素(电压+2×原始字节), 无alarm/state/Tp → **D-1** |
| SL427 AFN=0x82往返 | ✅ | 同上 |
| SL427 AFN=0x84往返+值验证 | ⚠️ | CRC通过；只解出1要素"电压"，无alarm/state/Tp → **D-1** |
| SL427 AFN=0x12四种模式 | ✅ | 0=兼容/1=自报/2=查询/3=调试 全部通过 |
| 充值量数值级验证 | ✅ | hex正确输出（34120000=1234 LE），但与解码器无往返验证 |
| 异常输入（空/非法/奇数/非7E） | ✅ | 全部正确抛 DecodeError |
| ASCII特殊值（零值/负数） | ✅ | 正确解码 |

### 10.3 源码审计结论

| 模块 | 行数 | 结论 |
|------|------|------|
| `sl651/decoder.py` | 569 | 逻辑正确，BCD→string 类型选择有争议（D-3），`_parse_elements` 循环健壮 |
| `sl651/encoder.py` | 311 | 核心正确，小时报 F5 不支持负数（D-2） |
| `sl427/decoder.py` | 402 | AFN=81/82/84 分支不拆分 aux（D-1），AFN=C0 分支正确 |
| `sl427/encoder.py` | 248 | 正确，`build_self_report_84` 的 alarm/state 恒=0 简化了问题 |
| `sl427/constants.py` | 151 | 0x0D 标签已知歧义（已注 TODO），AFN aux 集合常量死代码（已知） |
| `simulator/` | ~400 | 结构清晰，引擎/生成器/发送器无逻辑缺陷，加报机制合理 |
| `sl651/bcd.py` | 112 | BCD 编解码健壮，边界校验到位 |
| `sl651/crc.py` | 44 | CRC16/CRC8 实现正确（已用验证向量确认） |
| `tools/decode_cli.py` | 198 | CLI 工具正确，输入校验到位 |
| `web/app.py` | — | 未实际测试 |

---

## 十一、第二轮回归测试 — 主会话修复后验证

> 测试时间：2026-07-01 | 验证 D-1/D-2/D-3 修复 | `git diff HEAD~1` 确认改动

### 11.1 修复验证结果

| 缺陷 | 修复方案 | 验证结果 | 遗留问题 |
|------|----------|----------|----------|
| D-1 | AFN=81/82 新增 aux 拆分逻辑；AFN=84 独立分支解析电压+alarm+state+Tp | ⚠️ **部分通过** | **R-1: AFN=84 电压值计算错误** — 用 `int.from_bytes(volt_bytes, 'little')` 替代应使用的 `bcd_bytes_to_int_le`，导致 BCD 电压值被当原始整数解码 (12.3V → 46.56V)。0.0V 因为 0=0 碰巧正确 |
| D-2 | 负数水位编码为 `0xFFFF` (与 None 相同) | ✅ 通过 | 无 |
| D-3 | `_safe_bcd_val`/`_safe_hex_val` 改为返回 float/int 而非格式化字符串 | ✅ 通过 | 无 |

### 11.2 新发现缺陷（本轮/预先存在）

| 编号 | 严重度 | 文件:行 | 简述 |
|------|--------|---------|------|
| **R-1** | **Medium** | `sl427/decoder.py:399` | **D-1 修复引入的回归：AFN=84 电压值用 `int.from_bytes` 而非 `bcd_bytes_to_int_le`**。volt_bytes 是 BCD LE 编码，但被当原始小端整数解码。12.3V BCD LE = `[0x30,0x12]` → `int.from_bytes` = 4656 → 46.56V(错)，正确应为 `bcd_bytes_to_int_le` = 1230 → 12.30V |
| **R-2** | Low | `sl427/decoder.py:397` | **AFN=84 短数据（无 Tp）无 else 分支**：`if raw_len >= TP_LEN + 4` 不满足时返回 0 要素，未尝试降级解析电压部分 |
| **R-3** | Medium | `sl427/encoder.py:126,153` vs `sl427/decoder.py:159` | **alarm/state 编码-解码字节序不一致**（预先存在）：编码器用 `.to_bytes(2, 'little')`(LE)，`_parse_alarm`/`_parse_terminal` 用 `(data[0]<<8)\|data[1]`(BE)。示例：`alarm=0x0005 → LE=[05,00] → BE解码=0x0500`，bit0/bit2 全部错位。因所有测试 alarm/state=0 未被发现 |

### 11.3 回归测试基准

- 24/24 现有测试全部通过 ✅
- 福建 23 条 + 北京 25 条 CRC 全通过 ✅
- D-2/D-3 修复验证通过 ✅
- D-1 修复验证：alarm/state/Tp 已能解析 ✅，电压值计算错误 ❌

---

## 十二、第三轮回归测试 — R-1/R-2/R-3 修复验证

> 测试时间：2026-07-01 | `git diff HEAD~1`

### 12.1 变更确认

| 修复 | 变更 | diff 行 |
|------|------|---------|
| R-1 (电压值) | `int.from_bytes(volt_bytes, 'little')` → `bcd_bytes_to_int_le(volt_bytes) / 100` | `sl427/decoder.py` +2 |
| R-2 (短数据) | AFN=84 新增 `else: volt_val = bcd_bytes_to_int_le(data_field) / 100` | `sl427/decoder.py` +6 |
| R-3 (字节序) | `_parse_alarm`/`_parse_terminal` 中 `(data[0]<<8)\|data[1]` → `data[0]\|(data[1]<<8)` | `sl427/decoder.py` -2/+2 |

### 12.2 验证结果

| 测试项 | 结果 | 详情 |
|--------|------|------|
| 现有 24 项测试 | ✅ 全通过 | 无回归 |
| 福建 23 + 北京 25 | ✅ CRC全通过 | |
| R-1: 4 组电压值 | ✅ 全部正确 | 0/12.3/12.6/98.76 V 精确返回 |
| R-2: 短数据降级 | ✅ | 仅 2B 电压 → 解出 1 要素 "电压 12.30V" |
| R-3: alarm=0x0005 | ✅ bit0→停电, bit2→报警 | 14 alarm + 8 state 全部正确 |
| R-3: state=0x0001 | ✅ 终端工作模式→自报确认 | 与编码值一致 |
| SL427 AFN=0x81 | ✅ alarm/state/Tp 均已解析 | |
| SL427 AFN=0x82 | ✅ alarm/state/Tp 均已解析 | |
| SL427 AFN=0x84 | ✅ 电压+alarm+state+Tp 共计 21 要素 | |

### 12.3 结论

**D-1/D-2/D-3 及 R-1/R-2/R-3 全部修复验证通过。** 当前项目无已知缺陷。

---

## 十三、评估总结

1. **协议核心算法稳健**：CRC16/MODBUS、CRC8(0xE5)、定义符解析、负数BCD、SL427 控制域/地址域/Tp 经 8 轮审计+48 条真实报文验证，可信度高。
2. **D-2/D-3 修复到位**：小时报负数水位和 BCD 值类型问题已正确解决。
3. **D-1 修复有回归**：AFN=84 分支用 `int.from_bytes` 替代 `bcd_bytes_to_int_le` 导致电压值换算错误（10×量级），需立即修正。同时缺少 else 分支处理短数据。
4. **R-3 是隐藏较深的预先缺陷**：alarm/state 编解码字节序不一致，因测试用例 alarm=state=0 一直未暴露。影响所有 C0/81/82 有 alarm/state 数据的解码。
5. **建议下一任优先处理**：R-1（D-1 回归，简单修）> R-3（alarm/state 字节序，影响面大）> R-2（边界降级，影响小）。

---

## 十四、第四轮回归测试 — v1.9 审计修复验证

> 测试时间：2026-07-20 | 基准：`audit/audit_report_v1.9.md`（28 项缺陷） | 20 文件变更，1558+137-

### 14.1 测试套件结果

| 套件 | 结果 |
|------|------|
| `tests/test_sl651.py` (25 项) | ✅ 全通过 |
| `tests/test_round1_blindspots.py` (10 组) | ✅ 全通过（M-12 修复） |
| 福建 23 条真实报文 | ✅ 23/23 CRC 全通过 |
| 北京 25 条真实报文 | ✅ 25/25 CRC 全通过 |

### 14.2 Critical / Medium 缺陷修复验证

| 编号 | 缺陷 | 验证点 | 结果 |
|------|------|--------|------|
| C-1 | ASCII帧为私有方言 | 单SOH起始符、ASCII头结构、编解码往返 | ✅ |
| C-2 | AFN=81H数据域顺序 | alarm(2B)+data+state(2B)+Tp, bit0→停电, 水位正确 | ✅ |
| M-1 | 0x4A校时帧 | 正文=8B, 发报时间=校时目标值 | ✅ |
| M-2 | 0x37查询帧 | 正文=8B(仅流水号+发报时间), API改为`build_query_frame()` | ✅ |
| M-3 | 0x48恢复出厂 | 正文=9B(含98H标识符) | ✅ |
| M-4 | 流水号规则 | 下行帧流水号=0000 | ✅ |
| M-5 | 84H仅2B无Tp | L=9, 总帧长=14, 电压12.30V | ✅ |
| M-6 | B0响应尾部4B | 水位数=1(无幻影), 报警bit0=停电 | ✅ |
| M-7 | 综合参数三处错误 | COMP_BITS[3]=0x07(气象) | ✅ |
| M-8 | PW密码BCD格式 | 参数设置帧编码正确(需实物验证) | ✅ |
| M-9 | 报警/状态位 | D9温度超限存在, D2=有效/无效, D3=退出/投入 | ✅ |
| M-10 | 流量符号/单位 | byteLen=5, signed=True, unit=m³/s | ✅ |
| M-11 | 模拟器站类遮蔽 | RainStation→0x50, SoilStation→0x4D | ✅ |
| M-12 | round1脚本5项恒失败 | 10组全通过 | ✅ |

### 14.3 Low 级修复抽检

| 检查项 | 结果 |
|--------|------|
| L-1 报文标识按12位解析 | ✅ (body_len公式修正) |
| L-2 下行观测时间不显伪值 | ✅ `obs_time_display=""` |
| L-3 F0F0跳字节修正 | ✅ (与F1F1独立处理) |
| L-9 流水号off-by-one | ✅ 下行帧固定为0 |
| L-8 0x80标注厂商自定义 | ✅ 注释标注 |
| L-13 模拟器/Web | ✅ base_station地址校验增强 |

### 14.4 结论

**v1.9 审计 28 项缺陷全部修复验证通过。** 协议核心算法无回归，48 条真实报文 CRC 全部通过，ASCII 帧按规范表16重构，SL427 告警/响应/电压帧与规范对齐，模拟器站类遮蔽修复。

---

## 十五、第五轮回归测试 — v2.0 审计修复验证

> 测试时间：2026-07-28 | 基准：`audit/audit_report_v2.0.md`（3M+13L，0C） | 22 文件变更，1078+555-

### 15.1 测试套件结果

| 套件 | 结果 |
|------|------|
| `tests/test_sl651.py` (25 项) | ✅ 全通过 |
| `tests/test_round1_blindspots.py` (10 组) | ✅ 全通过 |
| 福建 23 条 + 北京 25 条 | ✅ CRC 全通过 |

### 15.2 v1.9 修复项回归复核

14 项 C/M 修复全部经异源帧构造保持有效 ✅（审计 §4 复核表逐项通过，不再重复验证）。

### 15.3 v2.0 新发现缺陷验证

| 编号 | 缺陷 | 验证结果 | 详情 |
|------|------|----------|------|
| M-1 | 综合参数对 array 型贪婪消耗 | ✅ | B0+flag=0xE0(流量5B+水位4B+雨量3B)：流量=1, 水位=1, 雨量=1，无幻影要素 |
| M-2 | 小时报F4雨量组编码2B→1B | ✅ | `rain_amounts=[0..11]`：F4要素=12组, 值 0.0~11.0mm 全部正确 |
| M-3 | 上行0x0E统计雨量误解析 | ✅ | type=0x01~0x04 均正确解析为4B(类型+3B数据)，数值12.34正确 |
| L-1 | ASCII非法字符抛ValueError | ✅ | 非HEX字符正确抛 `DecodeError` |
| L-2 | 空心跳帧IndexError | ✅ | 空data_field正确返回0要素，不崩溃 |
| L-1~L-13 | 其余Low项 | ✅ | 代码审计抽检通过 |

### 15.4 旁注

- M-3 统计雨量的类型标签（type=0x01→"小时", 0x02→"日"...）偏移1位，值解析正确不影响互通
- 主测试套件从 v1.9 的 24 项扩展到 25 项（新增 ASCII 往返测试）
- `test_round1_blindspots.py` 保持 10/10 全通过（M-12 修复保持有效）

---
