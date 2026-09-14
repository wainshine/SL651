# SL651-Toolkit 代码审计报告 v2.2

> 审计日期：2026-09-14  
> 审计角色：代码审计 3 代（只审不修）  
> 基线文档：`docs/project.md` v1.2.6、`README.md` v1.2.6  
> 基准代码：v1.2.6（`sl651/__init__.py:__version__ = "1.2.6"`）  
> 审计方式：四层审计模型（规约条文比对 / 需求实现对照 / 构造性回放 / 历史缺陷复核），全部问题经实际执行复现  
> 审计范围：`sl651/`、`sl427/`、`simulator/`、`tools/`、`web/`、`tests/`、`examples/`、全部文档

---

## 一、审计结论总览

| 严重度 | 数量 | 状态 | 说明 |
|--------|------|------|------|
| Critical (C) | 1 | 🆕 本轮新增 | 0x31 均匀报数据组重复格式未实现，静默丢弃数据 |
| Medium (M) | 5 | 🆕 本轮新增 | F5 真实报文定义符失配、84H 忽略 tp、异常契约不一致、测试仅验 CRC、body_len 静默掩码 |
| Low (L) | 7 | 🆕 本轮新增 | 弱断言/伪测试、静默空解析、地址误判、死常量、文档不一致等 |
| 历史缺陷复核 | 19 | ✅ 全部确认修复 | v2.1 的 H1~H4 / M1~M14 / R1~R5 逐条回放通过 |

**核心结论**：v1.2.6 的编解码主体（CRC16/MODBUS、CRC8/0xE5、定义符解析、负数 BCD、帧结构、SL427 控制域/地址域/Tp）经 12 轮审计 + 48 条真实报文验证，可信度高；**但 48 条真实报文的自动化验证仅校验 CRC，从未校验要素数量与数值**，导致两类真实报文的要素解析缺陷长期未被发现（C-1、M-1）。这两个缺陷是本轮最关键的发现。

---

## 二、严重缺陷（Critical）

### C-1 0x31 均匀时段水文信息报「数据组重复」格式未实现，静默丢弃数据

**位置**：`sl651/decoder.py:491` `SL651Decoder._parse_elements`（经 `sl651/decoder.py:456` 调用，调用处未传入功能码）

**规约依据**：
- §6.6.4.4 均匀时段水文信息报（功能码 31H），表30 上行正文结构：序号 7~9 为「要素标识符组」（标识符仅编列一次），序号 10~18 为「数据1.1、数据2.1、…、数据1.2、…」，即**标识符组只出现一次，其后按观测时间顺序连续编列各组数据**。
- 表30 注 d）："此类 HEX/BCD 编码报文中标识符规定的数据长度定义适用于其每组数据，即每组数据长度应一致。"
- 规定 b）："采用 HEX/BCD 编码结构时，均匀时段报只编列 1 个要素。"

**问题描述**：`_parse_elements` 是通用逐「引导符+定义符+单个数据」解析循环。对 0x31 帧，它在读到「引导符 39 + 定义符 23」后只消费**一个** 4 字节数据，随后把后续重复数据字节误当作新的引导符/定义符，通常因 `raw_hex` 为空而 `break`，从而静默丢弃其余全部数据组。`_decode_binary` 中虽计算了 `is_uniform = func == 0x31`，但该标志只写入结果对象，**从未用于改变解析行为**。

**实际验证**（`examples/fujian_messages.txt:15`，真实福建规定报文）：

```
帧: 7E7E 01 1000000006 00 31 004E 02 2F7E 221205110019 F1F1 1000000006 48 F0F0 2212051005
    04 18 000005             ← 时间步长码 = 5 分钟
    39 23 00028960           ← 要素标识符组（仅一次）
    00028960 × 11            ← 后续 11 组数据（无重复标识符）
    ...CRC
```

解码结果：

```
>>> 0x31 frame: raw data has 12x 00028960; decoder returned 1 water-level elements
04 时间步长 5 000005
39 瞬时河道水位 28.96 00028960
```

`data` 区共 55 字节 = `04 18 000005`(5) + `39 23`(2) + 12×4(48)，解码器**只输出 1 个水位要素，静默丢失 11/12 组数据**。

**影响范围**：所有 0x31 均匀报（等间隔时段水文信息，含水位、流量、雨量等）在 HEX/BCD 编码下均丢失除第一组外的全部数据。`project.md §2.2` 明确标注 `0x31 均匀报 解码 ✅`，属功能声明与实际不符。

**漏报原因**：
1. `tests/test_sl651.py:341` `test_fujian_messages` 只断言 `failed == 0`（CRC 通过）与 `success >= 20`，不校验要素数量/数值；CRC 与要素解析完全独立，故缺陷不可见。
2. `examples/fujian_messages.txt` 的注释（"2要素"）是按**有缺陷的解码器输出**回填的，注释与实现互相印证，形成闭环误导。
3. 历史审计（v1.4~v2.0）将「F4/F5 均匀报数组」判为 ✅，但从未对真实 0x31 报文做要素级回放。

**修复建议**（供开发参考，审计不改）：`_parse_elements` 接收功能码，对 `func==0x31` 采用「标识符组一次 + 按定义符长度重复消费剩余数据组」的解析策略（或至少在检测到长度不符时抛 `DecodeError`，而非静默截断）。

---

## 三、中等缺陷（Medium）

### M-1 F5 数组长度完全信任定义符，真实福建报文定义符失配导致截断 + 垃圾要素

**位置**：`sl651/decoder.py:729` `_parse_f5_array`；调用点 `sl651/decoder.py:556`

**规约依据**：附录 C 表 C.1 第 5、6 项明确 **F4H = 12 字节 HEX**（1 小时内每 5 分钟时段雨量）、**F5H~FCH = 24 字节 HEX**（1 小时内 5 分钟间隔相对水位，分辨率 0.01m）。§6.6.3.2 表26 规定定义符高 5 位=数据字节数、低 3 位=小数位。

**问题描述**：
1. `_parse_f5_array(raw_hex, f_len, code)` 用定义符解析出的 `f_len` 决定消费长度（`need_chars = f_len*2`），而非按规范固定 24 字节。
2. 该函数内部**硬编码 `/100`**（`f"{pv / 100:.2f}"`），完全忽略定义符的低 3 位小数位，与「长度信定义符、小数不信定义符」自相矛盾。

**实际验证**：

```
# 福建 0x34 小时报（examples/fujian_messages.txt:9）
F5 定义符 = 0x5C（高5位=11字节，低3位=4小数）
实际载荷 = 24 字节（12 组 × 2 字节）
解码结果: F5 要素 5 个（应为 12 个）

# 福建 0x34 小时报（examples/fujian_messages.txt:24）
F5 定义符 = 0x5C，实际载荷 24 字节
解码结果: F5 5 个 + 3 个垃圾要素 2D/0A/EC（应为 12 个 F5）
>>> 0x34 frame: F5 elems= 5 | spurious= [('2D', '2D'), ('0A', '0A2D0A2D0A'), ('EC', 'EC')]
```

对比北京水务报文（`examples/beijing_messages.txt:14`）F5 定义符 = `0xC0`（24 字节），解码出 12 个 F5 要素，正常。

**影响范围**：所有定义符非标准（非 0xC0/0xC2）的 F5~FC 真实报文会被截断并产生垃圾要素；0x34 帧第 2 条还会进一步把垃圾字节混入要素列表。同样地，F4 若定义符异常也会失配（当前样本 F4 定义符 0x60 正常）。

**漏报原因**：同 C-1，真实报文测试只验 CRC；且自产自销往返（编码器固定 0xC2）永远一致，无法暴露对第三方定义的鲁棒性问题。

**备注**：福建样本 F5 定义符 0x5C 与国标附录 C 固定 24 字节存在冲突（可能为厂商非标实现或样本笔误）。无论样本是否合规，解码器当前行为是「静默截断 + 伪造要素」，应改为固定 24 字节或在长度不符时显式报错。

### M-2 `SL427Encoder.build_self_report_84` 静默忽略 `tp` 参数

**位置**：`sl427/encoder.py:215`

**规约/文档依据**：
- 函数 docstring："自报电压帧 (AFN=84H, AUX=仅Tp)"。
- `project.md §3.6`：`build_self_report_84(voltage, tp)`。
- `sl427/decoder.py:522` 实现了 `raw_len >= TP_LEN + 4` 时解析 Tp 的分支（按声明应当存在）。

**问题描述**：函数签名含 `tp`，函数体却从不使用它，直接 `return self.build_frame(0x84, ctrl, data)`，无 `tp=` 传参。

**实际验证**：

```
>>> 84 without tp len= 14 6809688D1101080405843012A116
>>> 84 with    tp len= 14 6809688D1101080405843012A116
>>> same bytes? True
>>> decoded elements: [('电压', '12.30')]
```

传入 `tp=datetime(2026,6,1,12,0)` 与不传，字节完全一致。因此解码器 84H 的 Tp 分支是**死代码**，`test_round1_blindspots.py::test_sl427_84_roundtrip` 传了 `tp` 但只校验 CRC+AFN，未能发现。

**影响**：调用方以为写入了观测时间，实际缺失；与 docstring/`project.md` 声明矛盾。

### M-3 编码器 BCD 超限泄漏 `ValueError`，与 v1.2.5 统一异常契约不一致

**位置**：`sl651/encoder.py:33` `_encode_bcd` → `sl651/bcd.py:40` `int_to_bcd_bytes`（抛 `ValueError`）；同类问题见 `sl427/encoder.py:269` `build_set_recharge`、`sl427/encoder.py:224` `build_self_report_84`

**问题描述**：v1.2.5 已将两侧编码器参数校验统一为抛 `EncodeError`（见 `test_sl651_encoder_validation` / `test_sl427_encoder_validation`），但底层 BCD 值溢出仍走 `int_to_bcd_bytes` 的 `ValueError`，未做包装。

**实际验证**：

```
99999.9        no error          # data_len=3, dec=1 → 999999 ≤ 999999 上限，恰好合法
123456789.0    ValueError 值 1234567890 超出 3 字节 BCD 范围 (0~999999)
```

调用方按文档只捕获 `EncodeError` 时无法拦截该异常。`project.md §2.6` 虽注明"BCD 超限 → 抛 `ValueError`"，但与同版本编码器其余路径（`EncodeError`）不一致，属契约分裂。

**影响**：库对畸形输入的行为不统一；使用方 `except EncodeError` 会漏网。SL427 `build_set_recharge(-1)`、`build_self_report_84(999.99)` 同样泄漏 `ValueError`。

### M-4 真实报文测试只校验 CRC，不校验要素数量与数值

**位置**：`tests/test_sl651.py:341` `test_fujian_messages`、`tests/test_sl651.py:369` `test_beijing_messages`

**问题描述**：两个"真实报文验证"测试仅统计 `r.crc_ok`，断言 `failed == 0`（福建另加 `success >= 20`）。要素列表 `r.elements` 的数量、编码、数值完全未校验。

**证据**：
- 福建 0x31 帧丢失 11/12 组数据，测试仍通过（C-1）。
- 福建 0x34 帧产生 3 个垃圾要素，测试仍通过（M-1）。
- `examples/fujian_messages.txt` 注释的要素数（"5要素"/"2要素"/"12要素"）与实际解码输出（5/2/24）不一致，注释不可信。
- `test_fujian_messages` 的 `success >= 20` 允许最多 3 条报文解析失败，门槛过松。

**影响**：这是 C-1/M-1 长期漏报的**根因**，也是历史审计反复声称"48 条真实报文验证通过"却未发现数据错误的原因。CRC 自洽不能替代要素正确性验证。

### M-5 `build_frame` 未校验正文长度上限，>4095 字节静默掩码产生自产畸形帧

**位置**：`sl651/encoder.py:112`

**问题描述**：报文标识为 12 位正文长度（`project.md §2.1` / v1.2.3 修正项）。`build_frame` 计算 `body_len` 后直接 `ident_hi = (direction << 7) | ((body_len >> 8) & 0x0F)`，未校验 `body_len <= 4095`，超出部分被静默丢弃。

**实际验证**：

```
>>> body_len declared 914 actual body bytes 5002 -> masked? True
```

构造 5002 字节正文 → 标识声明 914 字节，产出的帧长度与标识不符，解码端将报"正文长度不匹配"。编码器应抛 `EncodeError`。`build_ascii_frame`（`sl651/encoder.py:413`）同样存在 12 位掩码。

---

## 四、轻微问题（Low）

| # | 位置 | 问题 | 验证 |
|---|------|------|------|
| L-1 | `tests/test_sl651.py:774` | `test_alert_edge_trigger` 是**伪测试**：不驱动 `StationRunner._run`，而是在测试内手动复刻 `raw and not _alert_active` 布尔逻辑，无法验证真实代码路径。 | 阅读确认 |
| L-2 | `tests/test_sl651.py:411` | `test_invalid_bcd_graceful` 只断言 `not crc_ok` 与 `isinstance(elements, list)`，未验证"无效 BCD 降级为 `-`"的实际行为；畸形帧 CRC 天然失败，断言恒真。 | 阅读确认 |
| L-3 | `sl427/decoder.py:444,493,522` | AFN=C0/81/82/84 在数据域短于 `TP_LEN+4` 时静默返回 0 要素，无降级/报错。实测 C0 携 4 字节数据 → `elems=0` 且 `crc_ok=True`。 | 构造回放 |
| L-4 | `sl427/decoder.py:290` | `_format_addr` 以 `addr[0] == 0x00` 判定方式2，方式1 行政区划码首位为 0 时被误判。实测 `00 01 08 10 00` → "方式2 站点编码: 01081000"。 | 构造回放 |
| L-5 | `sl427/constants.py:62` | `AFN_DATA_LEN` 定义后无人引用（死常量）；`AFN_NO_AUX`/`AFN_TP_ONLY`/`AFN_PW_TP`（`constants.py:135`）同样为文档用途死代码（handoff 已知）。 | grep 确认 |
| L-6 | `sl427/encoder.py:239` | `build_param_set_frame` 固定 `encode_pw(0, pw)`（key1 恒 0）；`pw > 999` 时 `encode_pw` 泄漏 `ValueError`。 | 阅读确认 |
| L-7 | 文档 | 见 §六 文档一致性清单 | 逐项核对 |

---

## 五、规约符合性复核（Layer 1）

### 5.1 SL651 核查表

| 核查项 | 代码位置 | 规约依据 | 结论 |
|--------|----------|----------|------|
| CRC-16/MODBUS（0xA001/初值0xFFFF） | `crc.py:12` | §6.5.2 表20 | ✅ `crc16(b"123456789")==0x4B37` |
| 定义符 高5位字节数/低3位小数位 | `constants.py:119` | §6.6.3.2 表26 | ✅ `parse_def_byte(0x23)==(4,3)` |
| 负数 BCD `0xFF` 前缀 | `encoder.py:33` / `decoder.py:119` | §6.6.3.3a | ✅ 往返 -0.345 |
| FUNC_MAP 23 项 | `constants.py:51` | 附录B 表B.1 | ✅ 实测 23 项 |
| SL651_ELEMENTS 101 项 | `constants.py:141` | 附录C 表C.1 | ✅ 实测 101 项 |
| SL651_ASCII_ELEMENTS 102 项 | `constants.py:251` | 附录C ASCII 列 | ✅ 实测 102 项 |
| STATION_TYPE 11 类 | `constants.py:79` | 附录A 表A.1 | ✅ |
| 上行表11 / 下行表12 地址顺序 | `decoder.py:377` / `encoder.py:117` | §6.5.2 表11/表12 | ✅ |
| F4 = 12 字节 / F5~FC = 24 字节 | `decoder.py:710,729` | 附录C 表C.1 | ⚠️ **长度信定义符而非固定值**（M-1） |
| 0x31 均匀报数据组重复格式 | `decoder.py:491` | §6.6.4.4 表30 + 注d | ❌ **未实现**（C-1） |
| 报文标识 12 位正文长度 | `encoder.py:113` | §6.4 表16 / v1.2.3 | ⚠️ 无 >4095 校验（M-5） |
| 流水号规则（下行=0、2F 不累加） | `encoder.py:104` | 表27 注 | ✅ |
| 45H 状态位 | `decoder.py:690` | 表58 | ⚠️ 缩减为 12 位（project.md 已知 P4） |

### 5.2 SL427 核查表

| 核查项 | 代码位置 | 规约依据 | 结论 |
|--------|----------|----------|------|
| CRC8（0xE5/初值0） | `crc.py:34` | §6.3.3.5 | ✅ `crc8(b"\x00\x01\x02")==0xA6` |
| 控制域 C 位布局（DIR/DIV/FCB/命令码） | `constants.py:143` | 表4 | ✅ |
| 地址域方式1（3B BCD + 2B BIN 小端） | `decoder.py:283` / `encoder.py:25` | §6.3.3.4 表7/表8 | ✅ |
| 地址域方式2（00H + nibble-packed） | 同上 | 表8 | ✅（首位 0 误判见 L-4） |
| Tp 7B（秒分时日月年 BCD + 延时 BIN） | `encoder.py:56` | §6.3.3.8 表10 | ✅ |
| AFN_MAP 30 项 | `constants.py:23` | 附录A | ✅ 实测 30 项 |
| CTRL_FUNC_MAP 16 项 | `constants.py:83` | 表5/表6 | ✅ 实测 16 项 |
| alarm/state 小端编解码一致 | `decoder.py:238,251` / `encoder.py:153` | §7.3.14 | ✅（R-3 已修） |
| AFN=81H alarm 在 data 前 | `decoder.py:498` / `encoder.py:188` | §7.5.2 | ✅ |
| AFN=84H 电压 2B | `decoder.py:522` / `encoder.py:224` | 表B.98 | ⚠️ 编码器忽略 `tp`（M-2） |
| AFN=FFH 尾部 Tp 剥离 | `decoder.py:553` | 用户自定义 | ✅ |

---

## 六、测试覆盖与盲区分析（Layer 3）

### 6.1 本轮回放结果

| 回放项 | 命令 | 结果 |
|--------|------|------|
| 主测试套件 | `python3 -B tests/test_sl651.py` | ✅ 44/44 通过 |
| 盲区测试套件 | `python3 -B tests/test_round1_blindspots.py` | ✅ 10/10 通过 |
| 福建 23 条 | `decode_cli sl651 --file examples/fujian_messages.txt` | ✅ 23/23 CRC 通过 |
| 北京 25 条 | `decode_cli sl651 --file examples/beijing_messages.txt` | ✅ 25/25 CRC 通过 |
| 0x31 均匀报要素回放 | 见 C-1 | ❌ 1/12 组 |
| 0x34 F5 要素回放 | 见 M-1 | ❌ 5/12 组 + 3 垃圾 |
| 84H tp 回放 | 见 M-2 | ❌ tp 被忽略 |
| BCD 溢出回放 | 见 M-3 | ❌ ValueError 泄漏 |
| body_len 掩码回放 | 见 M-5 | ❌ 5010→914 |

### 6.2 盲区标记

| 盲区 | 风险 | 本轮发现 |
|------|------|----------|
| **真实报文的要素级验证缺失** | 高 | C-1、M-1 |
| **0x31 均匀报重复数据组** | 高 | C-1 |
| **定义符与真实厂商实现差异** | 高 | M-1 |
| **编码器异常契约统一性** | 中 | M-3 |
| **编码器自产帧长度上限** | 中 | M-5 |
| **加报边沿触发的真实代码路径** | 中 | L-1 |
| **SL427 短数据域降级** | 低 | L-3 |
| **地址方式判定边界** | 低 | L-4 |

### 6.3 文档一致性清单（Layer 4 附带）

| # | 位置 | 不一致 |
|---|------|--------|
| D-1 | `project.md §2.1` vs `§2.5` | 前者写 ASCII 起始符 `01 01`，后者写单 `01`（实现支持单 SOH 新 ASCII + 双 SOH 旧方言） |
| D-2 | `project.md §2.6` | `build_frame(func, body, dir, ascii, end_marker)` 形参名与代码 `(function_code, body, direction, ascii_mode, end_marker, tx_time)` 不符（v1.2.6 已修 `sl651/README.md`，未修 `project.md`） |
| D-3 | `project.md §3.6` | 文档 `build_self_report_84(voltage, tp)`，实现忽略 `tp`（M-2） |
| D-4 | `sl651/README.md:5` | "覆盖上行 7 种 + 下行 4 种功能码" 与编码器实际方法数不符 |
| D-5 | `web/README.md:31` | "支持 `7E7E` 和 `0101`(ASCII)" 应为单 `01` |
| D-6 | `project.md §2.3` | STATUS 位描述列 11 项，`STATUS_BITS` 实为 12 项 |
| D-7 | `handoff_test.md §1.3` | L-3 仍写 `docs/project.md:309` 测试计数 "21 项"（现为 44） |
| D-8 | `handoff_test.md §8` | "COMP_BITS 气象映射 D3 位未含气压(0x07),仅含风速(0x08)" 与代码 `COMP_BITS[3]=0x07` 矛盾 |
| D-9 | `handoff_test.md §10.2` | 工作模式映射 "0=自报/1=查询/2=兼容/3=调试" 与 `project.md §3.2`、代码 docstring "0=兼容/1=自报/2=查询/3=调试" 矛盾 |
| D-10 | `handoff_test.md` | 章节顺序错乱（十四、十五 排在 十二、十三 之前） |
| D-11 | `examples/fujian_messages.txt` | 注释要素数（5/2/12）与解码输出（5/2/24）不一致，且是按缺陷输出回填 |

---

## 七、需求文档对照（Layer 2）

| `project.md` 声明 | 代码实现 | 结论 |
|-------------------|----------|------|
| §2.2 `0x31 均匀报 解码 ✅` | `_parse_elements` 无 0x31 专用逻辑 | ❌ 见 C-1 |
| §2.2 `0x32/33/34 解码 ✅` | 定时/加报正常；0x34 的 F5 依赖定义符 | ⚠️ 见 M-1 |
| §2.2 `0x30/35/36 解码 ✅` | 通用要素解析 | ✅（F3 图片已按 v1.2.6 字节摘要显示） |
| §2.2 下行 `0x37/40/48/4A 编码 ✅` | `build_query_frame`/`build_set_param_frame`/`build_reset_frame`/`build_clock_sync_frame` | ✅ |
| §2.6 `build_frame` 通用帧构造 ✅ | 存在；无 body_len 上限校验 | ⚠️ M-5 |
| §3.2 `AFN=84 编码 ✅ build_self_report_84` | 存在但忽略 `tp` | ⚠️ M-2 |
| §3.6 SL427 编码器 12 方法 | 全部存在 | ✅ |
| §4 模拟器站点/发送器/引擎/CLI ✅ | 全部存在，`add_station` 不崩 | ✅ |
| §5 CLI 解码工具 ✅ | `decode_cli` 双协议/text/json | ✅ |
| §6 Web 解码界面 ✅ | Flask 单文件，端口 5050 | ✅ |
| §7.1 测试 44 项全部通过 ✅ | 实测 44/44 | ✅ |
| §7.2 福建 23 条 CRC 验证 ✅ | 23/23 CRC 通过，但要素未验证 | ⚠️ M-4 |
| §7.3 北京 25 条 CRC 验证 ✅ | 25/25 CRC 通过，F5 正常 | ✅ |
| §8 P4 远期（多包拼接/45H 32位等） | 未实现，与文档一致 | ✅ 已知 |

---

## 八、历史审计对比（Layer 4）

### 8.1 v2.1 缺陷闭环复核（逐条回放）

| v2.1 编号 | 修复点 | 复核结果 |
|-----------|--------|----------|
| H1 | SL651 截断上行帧 `DecodeError` | ✅ `test_sl651_truncated_uplink` 通过 |
| H2 | SL427 非法 BCD 泄漏 → `DecodeError` | ✅ `test_sl427_malformed_bcd` 通过 |
| H3 | SL427 最小 L 校验 | ✅ 同上 |
| H4 | TcpSender 多线程加锁 | ✅ `test_tcp_sender_threadsafe` 通过 |
| M1~M5 | SL651 Hex型 0xFF / ASCII CRC / ST 站类 / 定义符 / 小时报超限 | ✅ `test_sl651_hex_type_ff`、`test_sl651_encoder_validation` 通过 |
| M6~M9 | SL427 地址/帧/PW/BCD 校验、FFH Tp 剥离 | ✅ `test_sl427_encoder_validation`、`test_sl427_ff_tp_strip` 通过 |
| M10~M12 | CLI YAML 校验、墒情温度、加报边沿 | ✅ 对应测试通过 |
| M13~M14 | Web 400、JSON/Web 脱敏 | ✅ `test_web_api`、`test_cli_json_masking` 通过 |
| R1~R5 | 综合参数偏移、入口校验、有符号 BCD、时间占位 | ✅ 对应测试通过 |
| v1.2.6 B1~B3 | 非法半字节时间、F3 图片、ASCII 保留标识符 | ✅ 对应测试通过 |

**结论**：v2.1 及 v1.2.6 的全部历史修复均落实且无回归。

### 8.2 与上一轮的关键差异

| 维度 | v2.1（2026-08-26） | v2.2（本轮） |
|------|--------------------|--------------|
| 新增 Critical | 0 | **1（0x31 均匀报数据丢失）** |
| 新增 Medium | 0（复核） | **5** |
| 验证方法 | 以自产帧往返为主 | 增加**真实报文要素级**回放 |
| 核心教训 | 异常契约/线程安全 | **"CRC 通过 ≠ 要素正确"，真实报文必须校验数值** |

---

## 九、附录：缺陷汇总表

| 编号 | 严重度 | 文件:行 | 简述 | 状态 |
|------|--------|---------|------|------|
| C-1 | Critical | `sl651/decoder.py:491` | 0x31 均匀报数据组重复格式未实现，丢失 11/12 组 | 🆕 新增 |
| M-1 | Medium | `sl651/decoder.py:729` | F5 长度信定义符（0x5C=11B vs 实际24B），截断+垃圾要素；小数硬编码 /100 | 🆕 新增 |
| M-2 | Medium | `sl427/encoder.py:215` | `build_self_report_84` 静默忽略 `tp` 参数 | 🆕 新增 |
| M-3 | Medium | `sl651/encoder.py:33`、`sl427/encoder.py:269,224` | BCD 溢出抛 `ValueError` 而非 `EncodeError` | 🆕 新增 |
| M-4 | Medium | `tests/test_sl651.py:341,369` | 真实报文测试仅验 CRC，不验要素数量/数值 | 🆕 新增 |
| M-5 | Medium | `sl651/encoder.py:112,413` | body_len >4095 静默掩码，自产畸形帧 | 🆕 新增 |
| L-1 | Low | `tests/test_sl651.py:774` | `test_alert_edge_trigger` 伪测试，不驱动 `_run` | 🆕 新增 |
| L-2 | Low | `tests/test_sl651.py:411` | `test_invalid_bcd_graceful` 弱断言 | 🆕 新增 |
| L-3 | Low | `sl427/decoder.py:444,493,522` | C0/81/82/84 短数据域静默 0 要素 | 🆕 新增 |
| L-4 | Low | `sl427/decoder.py:290` | 方式1 地址首位 0 被误判为方式2 | 🆕 新增 |
| L-5 | Low | `sl427/constants.py:62,135` | `AFN_DATA_LEN` 及 AUX 集合死常量 | 🆕 新增 |
| L-6 | Low | `sl427/encoder.py:239` | PW key1 恒 0；pw>999 泄漏 ValueError | 🆕 新增 |
| L-7 | Low | 文档 ×11 | 见 §6.3 D-1~D-11 | 🆕 新增 |

---

## 十、审计师评估

1. **协议核心算法稳定**：CRC16/MODBUS、CRC8/0xE5、定义符、负数 BCD、帧结构、SL427 控制域/地址域/Tp 经 12 轮 + 48 条真实报文验证，未发现算法级错误。
2. **最大系统性盲区**：真实报文的自动化验证长期停留在 CRC 层，未校验要素数量与数值。CRC 自洽会掩盖解析错误，本轮 C-1/M-1 即由此漏检 11 轮。
3. **最严重缺陷**：0x31 均匀报（C-1）静默丢失 11/12 组数据，且 `project.md` 将其标注为 ✅ 已支持。
4. **建议下一轮优先处理**：C-1（数据完整性，必修）> M-1（真实帧 F5 鲁棒性）> M-2（84H tp）> M-3（异常契约统一）> M-4（补要素级真实报文测试）。
5. **方法论建议**：将 `examples/fujian_messages.txt` 的要素数量/关键数值固化为测试基线（而非仅 CRC），并对每条真实报文增加「要素总数 + 首末要素值」断言。

> 本报告只审不修，未修改任何源码、测试或文档；所有结论均可由报告内命令复现。
