# SL651-Toolkit 代码审计报告 v2.3

> 审计日期：2026-09-14  
> 审计角色：代码审计 4 代（只审不修）  
> 基线文档：`docs/project.md` v1.3.0、`README.md` v1.3.0、`docs/handoff_main.md` v1.3.0  
> 基准代码：v1.3.0（`sl651/__init__.py:__version__ = "1.3.0"`）  
> 审计方式：四层审计模型（规约条文比对 / 需求实现对照 / 构造性回放 / 历史缺陷复核），全部问题经实际执行复现  
> 审计范围：`sl651/`、`sl427/`、`simulator/`、`tools/`、`web/`、`tests/`、`examples/`、全部文档  
> 规约依据：`行业规范/水文监测数据通信规约SL651-2014.txt`、`行业规范/水资源监测数据传输规约SL427-2021.txt`

---

## 一、审计结论总览

| 严重度 | 数量 | 状态 | 说明 |
|--------|------|------|------|
| Critical (C) | 0 | — | 核心算法（CRC16/MODBUS、CRC8/0xE5、定义符、负数 BCD、帧结构、控制域/地址域/Tp）未发现新缺陷 |
| Medium (M) | 4 | 🆕 本轮新增 | FUNC_MAP 功能码名称与规约矛盾、SL427 查询响应对 0xAA 填充报错、人工置数报编解码契约不一致、地址/信道编码缺长度校验 |
| Low (L) | 6 | 🆕 本轮新增 | AFN=5CH 名称错误、ASCII 多包方向位丢失、死标识符项、0x26 量程注释不符、示例注释沿用错误功能码名、测试计数文档漂移 |
| 历史缺陷复核 | v2.2 的 1C+5M+7L | ✅ 全部确认修复 | 0x31 均匀报 / F5 固定长度 / 84H 去 tp / BCD 溢出契约 / 正文长度上限 / 真实报文要素级基线 等逐条回放通过 |

**核心结论**：v1.3.0 新增的 SL427 全 AFN、SL651 编码器补全与多包重组，其算法主体与规约一致；v2.2 的全部缺陷均已落实修复且无回归。本轮 4 项 Medium 中，**M-1（SL651 功能码名称表与规约/需求/编码器三方矛盾）** 影响面最广：它使解码输出的 `function_name` / `message_type` 对 0x38/0x42/0x43/0x45/0x46/0x47/0x50/0x51 系统性错误，且 0x44 直接显示「未知」，而该错误映射又长期被 `examples/fujian_messages.txt` 的注释「互相印证」，与 v2.2 的 C-1/M-1 漏报模式同源。

---

## 二、严重缺陷（Critical）

无。

核心编解码路径经 13 轮审计 + 48 条真实报文验证，本轮未发现核心功能不可用、数据完整性彻底破坏或崩溃类缺陷。

---

## 三、中等缺陷（Medium）

### M-1 `sl651/constants.py` `FUNC_MAP` 功能码名称与规约、`project.md`、编码器三方矛盾

**位置**：`sl651/constants.py:51`（`FUNC_MAP`），错误项：`:63`(0x38)、`:67`(0x42)、`:68`(0x43)、`:69`(0x45)、`:70`(0x46)、`:71`(0x47)、`:75`(0x50)、`:76`(0x51)

**规约依据**（SL651-2014 正文逐条）：

| 功能码 | 规约原文 | 位置 | 代码 FUNC_MAP 现值 | 判定 |
|--------|----------|------|--------------------|------|
| 38H | 中心站查询遥测站指定要素的时段数据 | 规约行 2072 | 修改运行参数 | ❌ |
| 39H | 中心站查询遥测站人工置数 | 规约行 2168 | **缺失** | ❌ |
| 42H | 中心站修改遥测站运行参数配置表 | 规约行 2426 | 修改报警阈值 | ❌ |
| 43H | 中心站读取遥测站运行参数配置表 | 规约行 2429 | 读取报警阈值 | ❌ |
| 44H | 中心站查询水泵电机实时工作数据 | 规约行 2434 | **缺失** | ❌ |
| 45H | 查询遥测站软件版本信息 | 规约行 2530 | 修改水文参数 | ❌ |
| 46H | 查询遥测站状态及报警信息 | 规约行 2576 | 读取水文参数 | ❌ |
| 47H | 遥测站固态数据区全部初始化 | 规约行 2678 | 修改排水参数 | ❌ |
| 50H | 查询遥测站事件记录 | 规约行 3234 | 远程升级 | ❌ |
| 51H | 查询遥测站时钟 | 规约行 3365 | 查询版本 | ❌ |
| 4BH~4FH | IC卡状态 / 水泵 / 阀门 / 闸门 / 水量定值控制 | 规约行 2863~3185 | **缺失** | ❌ |

同时，`project.md §2.2` 的功能码表（0x42=修改运行参数、0x43=读取运行参数、0x45=查询软件版本、0x46=查询状态及报警、0x47=初始化固态存储、0x50=查询事件记录、0x51=查询时钟）与编码器方法语义（`build_query_software_version`=0x45、`build_query_status_alarm`=0x46、`build_init_solid_storage`=0x47、`build_query_event_record`=0x50、`build_query_clock`=0x51）**均与规约一致**，唯 `FUNC_MAP` 为离群值。

**实际验证**（编码器产出 → 解码器回读功能码名称）：

```
$ python3 -B -c "from sl651 import SL651Encoder, SL651Decoder; ..."
query_pump_data          -> 0x44 name=未知(0x44)
query_software_version   -> 0x45 name=修改水文参数
query_status_alarm       -> 0x46 name=读取水文参数
query_event_record       -> 0x50 name=远程升级
query_clock              -> 0x51 name=查询版本
```

解码器对自身编码器产出的帧给出错误甚至「未知」的功能码名称，属内部自相矛盾。

**影响范围**：
1. `DecodedMessage.function_name` / `message_type` 在 `project.md §2.2` 声明的 8 个功能码上系统性错误，CLI/Web/JSON 输出全部受污染。
2. 0x44 帧直接显示「未知(0x44)」，与 `project.md §2.6`（`build_query_pump_data` ✅）不符。
3. `examples/fujian_messages.txt` 注释（0x45 修改水文参数、0x47 修改排水参数、0x50 远程升级、0x51 查询版本、0x42 修改报警阈值、0x43 读取报警阈值、0x38 修改运行参数）按错误 `FUNC_MAP` 回填，形成「注释与实现互相印证」的闭环（与 v2.2 C-1 漏报模式同源，见 §6.2）。

**漏报原因**：
1. `tests/test_sl651.py` 的下行帧测试（`test_sl651_downlink_queries`、`test_sl651_config_and_manual_frames` 等）只断言 `function_code`、方向、结束符，**从不校验 `function_name`**。
2. 福建/北京真实报文基线只断言 `function_code` + 要素数 + 首末值，同样不校验功能码名称。
3. 历史审计（v1.4~v2.2）的 Layer 1 检查表虽列出「FUNC_MAP 23 项」并判 ✅，但只数条目数，未逐项与规约正文比对名称。

**修复建议**（供开发参考，审计不改）：按规约正文重写 `FUNC_MAP` 的 0x38~0x51 名称，补齐 0x39/0x44/0x4B~0x4F，并同步修正 `examples/fujian_messages.txt` 注释；为功能码名称增加一条「编码→解码名称一致」回归测试。

---

### M-2 SL427 查询/控制响应解析对规约合法的 `0xAA`/`0xFF` 缺测填充抛 `DecodeError`

**位置**：`sl427/decoder.py:392` `_parse_query_response`、`sl427/decoder.py:550` `_parse_control_response`；对比 `sl427/decoder.py:81` `_parse_ctrl_func_data`（**有**填充处理）

**规约依据**：SL427-2021 正文明确 `0xAA` 为「未采集/无数据」占位——规约行 1172「如仪表只监测其中一类参数，则另一类参数值用 `AAAAAAAAAA` 代替」；规约行 900「若无备用信道，备用信道类型码和中心站地址码为 `0xAAAA`，共 2 个字节」。`_parse_ctrl_func_data` 已实现 `0xAA`/`0xFF` 填充跳过（`decoder.py:101-109`），说明该约定为项目已知。

**问题描述**：`_parse_query_response` / `_parse_control_response` 的多个分支直接调用 `bcd_bytes_to_int_le`（非法半字节抛 `ValueError`），既无填充判断也无 try/except；`ValueError` 经 `SL427Decoder.decode` 统一包装为 `DecodeError`，导致**整帧合法报文被判定为解码失败**，而非降级显示 `-`。

**实际验证**（构造 CRC 正确的上行响应，数据域为规约允许的 0xAA 填充）：

```
$ python3 -B -c "...构造 AFN=50/55/56/62 响应, 数据域全 0xAA..."
0x50 RAISED DecodeError 报文解析失败: 无效 BCD 字节: 0xAA
0x55 RAISED DecodeError 报文解析失败: 无效 BCD 字节: 0xAA
0x56 RAISED DecodeError 报文解析失败: 无效 BCD 字节: 0xAA
0x62 RAISED DecodeError 报文解析失败: 无效 BCD 字节: 0xAA
```

受影响分支至少包括：50（站点地址）、53（自报间隔，`data[2:]` 为 BCD）、55（充值量）、56（报警值）、57（水位基值/上下限）、58（水压上下限）、59/5A（水质值）、62（转发站地址）、64（流量上限）、96（密码响应）。

**影响范围**：现场设备对「未采集」参数回填 `0xAA` 是规约行为，当前实现会把这类完全合法的响应帧判为失败，Web/CLI 显示「解码失败」，掩盖其余有效要素。

**漏报原因**：
1. `tests/test_sl427_query_afn.py` / `test_sl427_control_afn.py` 全部使用规整的 BCD 数据，**从不构造 0xAA 填充响应**。
2. `tests/test_fuzz_decoders.py` 只断言「仅抛受控 `DecodeError`」，而本缺陷恰好以 `DecodeError` 形式出现，被该断言**豁免**（`ALLOWED = (SL651DecodeError, SL427DecodeError)`），变异测试无法区分「合法帧被拒」与「畸形帧被拒」。

**修复建议**：在 `_parse_query_response` / `_parse_control_response` 的 BCD 解析处复用 `_parse_ctrl_func_data` 的填充跳过逻辑，或对非法半字节降级为 `-` 并写入 `warnings`。

---

### M-3 `SL651Encoder.build_manual_frame` 与解码器 F2 处理契约不一致，人工置数数据被静默丢弃

**位置**：`sl651/encoder.py:419` `build_manual_frame`；对应解码路径 `sl651/decoder.py:712`（`code == "ff"` 前的 F2 分支）与 `sl651/constants.py:145`（`"f2": (..., "Hex")`）

**需求/规约依据**：`project.md §2.6` 声明 `build_manual_frame(payload)` = 「人工置数报（F2 标识符 + 原编码数据）」；规约 §6.6.4.8 人工置数报功能码 35H（规约行 1894）。

**问题描述**：编码器产出正文为 `F2H + payload`（F2 后**无定义符**）；而解码器 `_parse_elements` 对任何引导符都按「引导符(1B) + 定义符(1B) + 数据」解析，`F2` 会被当作 `payload[0]` 作为定义符，若声明长度超过剩余数据则 `break`，最终**不产出任何要素**。

**实际验证**：

```
$ python3 -B -c "from sl651 import SL651Encoder, SL651Decoder; ..."
manual func 0x35 elements []
```

`build_manual_frame(bytes.fromhex("0102030405"))` 编码成功、CRC 通过，但解码 `elements == []`，人工置数载荷静默丢失。`examples/fujian_messages.txt:27` 的真实 0x35 帧（`F2F2...`）同样解出 0 要素（`FUJIAN_BASELINE` 记为 0 要素），与该契约问题一致。

**影响范围**：人工置数报（0x35）在 HEX/BCD 编码下的数据无法被本工具还原，`project.md §2.2`「0x35 解码 ✅」名不副实。

**漏报原因**：`tests/test_sl651_config_and_manual_frames` 仅断言 `crc_ok`、`function_code`、`direction`，不检查 `elements`；福建基线把 0x35 的期望要素数写成 0（按缺陷输出回填），与 v2.2 C-1 的漏报模式完全相同。

**修复建议**：统一 F2 的正文契约——或编码器补写定义符，或解码器对 `F2` 按「原编码剩余全部字节」处理（并校验编码端一致）。

---

### M-4 SL427 `build_set_addr` / `build_set_channel` 缺数据域长度校验，可产出畸形帧

**位置**：`sl427/encoder.py:262` `build_set_addr`、`sl427/encoder.py:601` `build_set_channel`

**规约依据**：AFN=10H「设置地址」数据域固定 5B（规约表 B.3）；AFN=A2H「设置主备信道类型及中心站地址」主/备信道地址长度由类型码决定（规约行 900）。同类方法 `build_set_relay_addr`（`encoder.py:396`）已对每项做 `len(a) != 5` 校验，`build_frame`（`encoder.py:119`）仅校验整帧地址域长度，**不校验 `data` 内容**。

**实际验证**：

```
$ python3 -B -c "..."
build_set_addr(1B) produced frame len 22 L= 17          # 数据域 1B，应为 5B
build_set_channel(1B addr) produced L= 20               # 主信道地址 1B，应为 7B/3B
```

传入长度错误的地址不报错，直接生成结构不合规的下行帧。

**影响范围**：调用方误传短地址时，库不拦截，产出自产畸形帧（对端将按规约解析出错误地址），且与同库其他便捷方法的校验契约不一致。

**漏报原因**：`tests/test_sl427_encoder_validation.py` 的校验用例集中在 `encode_address` / `encode_tp` / `build_frame` / `encode_pw`，未覆盖 `build_set_addr` / `build_set_channel` 的数据域长度。

**修复建议**：`build_set_addr` 校验 `len(new_addr_bytes) == 5`；`build_set_channel` 按类型码校验地址长度，超限抛 `EncodeError`。

---

## 四、轻微问题（Low）

| # | 位置 | 问题 | 验证 |
|---|------|------|------|
| L-1 | `sl427/constants.py:59` | `AFN_MAP[0x5C] = "查询剩余水量报警值"`，但规约行 101 与 `build_query_history_daily()`（`encoder.py:513`）均为「查询终端机历史日记录」。解码 0x5C 帧的 `afn_name` 错误；且不存在「查询剩余水量报警值」这一 AFN。 | 规约原文比对 + 代码阅读 |
| L-2 | `sl651/decoder.py:419` | ASCII 多包重组 `ident_raw = ((first[19] & 0x80)) | ...`：字节 19 是 ASCII 十六进制字符（如 `'0'=0x30`，高 bit 恒 0），无法承载方向位，重组后方向被强制为 0（上行）。二进制分支 `first[11] & 0x80` 正确。SYN 多包实际均为上行，影响有限。 | 阅读确认 |
| L-3 | `sl651/constants.py:268` | `SL651_ASCII_ELEMENTS["DRxnn"]` 为占位键，真实 token（如 `DRN05`）由 `_ascii_time_step_desc` 单独识别，该键**永不命中**（死项），且未随 `test_sl651_ascii_uniform` 更新。 | grep + 阅读确认 |
| L-4 | `simulator/rain_station.py:30` | 0x26 降水量累计值使用 `data_len=3`（BCD 上限 99999.9），但同行注释与 `handoff_main.md §五` 均称 `N(6,1)`（6 位整数）。量程与注释不符（当前上限约 5 位整数）。 | 阅读确认 |
| L-5 | `examples/fujian_messages.txt:47,56,59,68,71` 等 | 注释沿用 M-1 的错误功能码名称（0x45 修改水文参数 / 0x47 修改排水参数 / 0x50 远程升级 / 0x51 查询版本 / 0x42 修改报警阈值 / 0x43 读取报警阈值 / 0x38 修改运行参数），与规约及 `project.md` 矛盾。 | 逐行核对 |
| L-6 | `docs/handoff_test.md` §1.2、§14.1、§15.1 | 测试计数写 24/25 项，与当前 57 项不符（§3.1 已注明为「v1.1 基线快照」，但 §1.2 标题为「当前测试状态」，易误导）。属文档漂移，非功能缺陷。 | 文档核对 |

---

## 五、规约符合性复核（Layer 1）

### 5.1 SL651 核查表

| 核查项 | 代码位置 | 规约依据 | 结论 |
|--------|----------|----------|------|
| CRC-16/MODBUS（0xA001/初值 0xFFFF） | `crc.py:12` | §6.5.2 表20 | ✅ `crc16(b"123456789")==0x4B37` |
| 定义符 高5位字节数/低3位小数位 | `constants.py:119` | §6.6.3.2 表26 | ✅ `parse_def_byte(0x23)==(4,3)` |
| 负数 BCD `0xFF` 前缀 | `encoder.py:33` / `decoder.py:136` | §6.6.3.3a | ✅ 往返 -0.345 |
| FUNC_MAP 功能码名称 | `constants.py:51` | 附录B / 正文 6.6.4 | ❌ 0x38/0x42/0x43/0x45/0x46/0x47/0x50/0x51 错误，缺 0x39/0x44/0x4B~0x4F（**M-1**） |
| SL651_ELEMENTS 101 项 | `constants.py:141` | 附录C 表C.1 | ✅ 实测 101 项 |
| SL651_ASCII_ELEMENTS 102 项 | `constants.py:251` | 附录C ASCII 列 | ⚠️ 计数 102 正确，含死项 `DRxnn`（**L-3**） |
| STATION_TYPE 11 类 | `constants.py:79` | 附录A 表A.1 | ✅ |
| 上行表11 / 下行表12 地址顺序 | `decoder.py:559` / `encoder.py:126` | §6.5.2 表11/表12 | ✅ |
| F4 = 12B / F5~FC = 24B 固定 | `decoder.py:729,751` | 附录C 表C.1 | ✅ 失配写 `warnings` 并按固定值解析 |
| 0x31 均匀报数据组重复格式 | `decoder.py:772,786` | §6.6.4.4 表30 注d | ✅ 标识符组一次 + 多组数据 |
| 报文标识 12 位正文长度 + ≤4095 校验 | `encoder.py:117` | §6.4 表16 / v1.2.7 M-5 | ✅ 超限抛 `EncodeError` |
| 人工置数报 0x35 正文契约 | `encoder.py:419` / `decoder.py:712` | §6.6.4.8 | ❌ 编解码契约不一致（**M-3**） |
| 流水号规则（下行=0、2F 不累加） | `encoder.py:109` | 表27 注 | ✅ |
| 45H 状态位 | `decoder.py:958` | 表58 | ✅ 12 位（规约表58 仅定义 BIT0~11） |

### 5.2 SL427 核查表

| 核查项 | 代码位置 | 规约依据 | 结论 |
|--------|----------|----------|------|
| CRC8（0xE5/初值 0） | `crc.py:34` | §6.3.3.5 | ✅ `crc8(b"\x00\x01\x02")==0xA6` |
| 控制域 C 位布局（DIR/DIV/FCB/命令码） | `constants.py:207` | 表4 | ✅ |
| 地址域方式1（3B BCD + 2B BIN 小端） | `decoder.py:644` / `encoder.py:33` | §6.3.3.4 表7/表8 | ✅ |
| 地址域方式2（00H + nibble-packed） | 同上 | 表8 | ✅（`00H` 判定依据已在 docstring 说明） |
| Tp 7B（秒分时日月年 BCD + 延时 BIN） | `encoder.py:64` | §6.3.3.8 表10 | ✅ |
| AFN_MAP 61 项 | `constants.py:23` | 附录A | ⚠️ 数量正确，0x5C 名称错误（**L-1**） |
| CTRL_FUNC_MAP 16 项 | `constants.py:146` | 表5/表6 | ✅ |
| alarm/state 小端编解码一致 | `decoder.py:240,253` / `encoder.py:161` | §7.3.14 | ✅ |
| AFN=84H 电压 2B 无 Tp | `decoder.py:891` / `encoder.py:223` | 表B.98 | ✅ |
| AFN=81H alarm 在 data 前 | `decoder.py:855` | §7.5.2 | ✅ |
| 查询响应 0xAA/0xFF 缺测填充 | `decoder.py:392,550` | 规约行 1172/900 | ❌ 未处理，抛 `DecodeError`（**M-2**） |
| 参数设置数据域长度校验 | `encoder.py:262,601` | 表B.3 / 行900 | ❌ 缺失（**M-4**） |
| AFN=FFH 尾部 Tp 剥离 | `decoder.py:914` | 用户自定义 | ✅ |

---

## 六、测试覆盖与盲区分析（Layer 3）

### 6.1 本轮回放结果

| 回放项 | 命令 | 结果 |
|--------|------|------|
| 统一测试入口 | `python3 -B tests/run_all.py` | ✅ 8/8 套件通过 |
| 主测试套件 | `python3 -B tests/test_sl651.py` | ✅ 57/57 通过 |
| 福建 23 条 | `decode_cli sl651 --file examples/fujian_messages.txt` | ✅ CRC + 要素级基线通过 |
| 北京 25 条 | `decode_cli sl651 --file examples/beijing_messages.txt` | ✅ CRC + 要素级基线通过 |
| 功能码名称回放 | 见 M-1 | ❌ 0x44 未知 / 0x45~0x51 名称错误 |
| SL427 0xAA 填充回放 | 见 M-2 | ❌ AFN 50/55/56/62 抛 `DecodeError` |
| 人工置数报往返 | 见 M-3 | ❌ 解码 0 要素 |
| 地址长度校验回放 | 见 M-4 | ❌ 1B 地址未报错 |

### 6.2 盲区标记

| 盲区 | 风险 | 本轮发现 |
|------|------|----------|
| **解码输出字段的语义正确性（功能码名称）** | 高 | M-1 |
| **规约合法的「缺测」占位（0xAA/0xFF）鲁棒性** | 高 | M-2 |
| **编码器/解码器同一要素的契约一致性** | 中 | M-3 |
| **便捷方法的数据域长度校验一致性** | 中 | M-4 |
| **示例报文注释的可信度（按缺陷输出回填）** | 中 | M-1、L-5 |
| **变异测试的断言粒度（DecodeError 豁免合法帧）** | 中 | M-2 漏报根因 |
| **文档与代码的计数/名称同步** | 低 | L-6 |

### 6.3 文档一致性清单

| # | 位置 | 不一致 |
|---|------|--------|
| D-1 | `sl651/constants.py:51` vs `project.md §2.2` / 规约正文 | FUNC_MAP 名称错误（M-1） |
| D-2 | `sl427/constants.py:59` vs 规约行 101 / `encoder.py:513` | AFN=5CH 名称错误（L-1） |
| D-3 | `examples/fujian_messages.txt` 注释 vs 规约/`project.md` | 功能码名称沿用错误映射（L-5） |
| D-4 | `simulator/rain_station.py:30` vs 注释/`handoff_main.md §五` | 0x26 量程 `N(6,1)` 与 `data_len=3` 不符（L-4） |
| D-5 | `docs/handoff_test.md` §1.2/§14/§15 vs 实际 57 项 | 测试计数漂移（L-6） |
| D-6 | `sl651/constants.py:268` vs `decoder.py:121` | `DRxnn` 占位键死项（L-3） |

---

## 七、需求文档对照（Layer 2）

| `project.md` v1.3.0 声明 | 代码实现 | 结论 |
|--------------------------|----------|------|
| §2.2 `0x2F/30/31/32/33/34/35 解码 ✅` | 对应解码路径存在 | ✅ |
| §2.2 `0x37/44/45/46/47/48/49/4A/50/51 编码 ✅` | 方法均存在 | ✅ |
| §2.2 功能码名称（0x42/43/45/46/47/50/51） | `FUNC_MAP` 名称与文档矛盾 | ❌ M-1 |
| §2.2 `0x44 查询水泵电机数据 解码 —` | `build_query_pump_data` 产出 0x44，解码显示「未知」 | ⚠️ M-1 |
| §2.2 `0x35 人工置数报 解码 ✅` | 解码 0 要素 | ❌ M-3 |
| §2.6 `build_manual_frame` = F2 标识符 + 原编码 | 编码遵循，但解码器 F2 契约不同 | ❌ M-3 |
| §2.6 `build_frame` 正文 >4095 抛 EncodeError | `encoder.py:118` | ✅ |
| §3.2 `AFN=84 编码 ✅ build_self_report_84` | 签名无 tp，表B.98 一致 | ✅ |
| §3.2 `50~65 查询响应 ✅ _parse_query_response` | 分支齐全，但 0xAA 填充失败 | ⚠️ M-2 |
| §3.6 SL427 编码器方法表 | 全部存在 | ✅ |
| §4 模拟器站点/发送器/引擎/CLI ✅ | 全部存在，端到端测试通过 | ✅ |
| §5 CLI 解码工具 ✅ | 双协议/text/json | ✅ |
| §6 Web 解码界面 ✅ | Flask 单文件，端口 5050 | ✅ |
| §7.1 测试 57 项全部通过 ✅ | 实测 57/57 | ✅ |
| §7.2 福建 23 条 + §7.3 北京 25 条 ✅ | CRC + 要素级基线通过 | ✅ |
| §8 P4 远期（5CH 响应/下行解码等） | 未实现，与文档一致 | ✅ 已知 |

---

## 八、历史审计对比（Layer 4）

### 8.1 v2.2 缺陷闭环复核（逐条回放）

| v2.2 编号 | 修复点 | 复核结果 |
|-----------|--------|----------|
| C-1 | 0x31 均匀报「标识符组一次 + 多组数据」 | ✅ `test_sl651_uniform_report` 12/12 组通过 |
| M-1 | F4/F5 固定 12B/24B + `warnings` | ✅ `test_sl651_f5_fixed_length` 通过 |
| M-2 | 84H 去 `tp`，仅 2B 电压 | ✅ `test_sl427_84_no_tp` 通过 |
| M-3 | BCD 溢出统一 `EncodeError` | ✅ `test_sl651_bcd_overflow_contract` / `test_sl427_bcd_overflow_contract` 通过 |
| M-4 | 真实报文要素级基线 | ✅ `FUJIAN_BASELINE` / `BEIJING_BASELINE` 生效 |
| M-5 | 正文 >4095 抛 `EncodeError` | ✅ `test_sl651_body_len_limit` 通过 |
| L-1 | 加报边沿驱动真实 `_run` | ✅ `test_alert_edge_trigger` 通过 |
| L-2 | 无效 BCD 强断言 | ✅ `test_invalid_bcd_graceful` 通过 |
| L-3 | C0 短数据域降级 + `warnings` | ✅ `test_sl427_short_data_degrade` 通过 |
| L-4 | 地址方式判定文档化 | ✅ `test_sl427_addr_method` 通过 |
| L-5 | 死常量标注 | ✅ `AFN_DATA_LEN` / AUX 集合已注「文档用途」 |
| L-6 | PW key1 校验 | ✅ `build_param_set_frame` 预校验；`encode_pw` 仍抛 `ValueError`（内部 helper，未外泄） |
| L-7 | 文档 D-1~D-11 | ✅ 大部分已修；L-5/L-6 为本轮新发现的文档漂移 |

**结论**：v2.2 及 v1.2.7 的全部 C/M 修复均落实且无回归；L 级仅剩文档类漂移（本轮 L-6 记录）。

### 8.2 与上一轮的关键差异

| 维度 | v2.2（2026-09-14，基线 v1.2.6） | v2.3（本轮，基线 v1.3.0） |
|------|--------------------------------|---------------------------|
| 新增 Critical | 1（0x31 均匀报数据丢失） | 0 |
| 新增 Medium | 5 | 4 |
| 检查重点 | 真实报文的**要素数值** | 解码输出的**字段语义** + 规约合法占位鲁棒性 |
| 核心教训 | 「CRC 通过 ≠ 要素正确」 | 「要素数正确 ≠ 字段语义正确；受控异常 ≠ 合法输入不被拒」 |
| 新增功能覆盖 | — | SL427 全 AFN（50~65/90~96/A0~A2）、SL651 多包重组、编码器补全 |

---

## 九、附录：缺陷汇总表

| 编号 | 严重度 | 文件:行 | 简述 | 状态 |
|------|--------|---------|------|------|
| M-1 | Medium | `sl651/constants.py:51,63,67-71,75,76` | FUNC_MAP 0x38/0x42/0x43/0x45/0x46/0x47/0x50/0x51 名称与规约/需求/编码器矛盾，缺 0x39/0x44/0x4B~0x4F | 🆕 新增（长期存在） |
| M-2 | Medium | `sl427/decoder.py:392,550` | 查询/控制响应对规约合法 0xAA/0xFF 缺测填充抛 DecodeError | 🆕 新增 |
| M-3 | Medium | `sl651/encoder.py:419` / `sl651/decoder.py:712` | 人工置数报 F2 编解码契约不一致，载荷静默丢失 | 🆕 新增 |
| M-4 | Medium | `sl427/encoder.py:262,601` | build_set_addr / build_set_channel 缺数据域长度校验 | 🆕 新增 |
| L-1 | Low | `sl427/constants.py:59` | AFN=5CH 名称错误（应为历史日记录） | 🆕 新增 |
| L-2 | Low | `sl651/decoder.py:419` | ASCII 多包重组方向位丢失（恒判上行） | 🆕 新增 |
| L-3 | Low | `sl651/constants.py:268` | `SL651_ASCII_ELEMENTS["DRxnn"]` 死项 | 🆕 新增 |
| L-4 | Low | `simulator/rain_station.py:30` | 0x26 量程与 N(6,1) 注释不符 | 🆕 新增 |
| L-5 | Low | `examples/fujian_messages.txt` | 注释沿用 M-1 的错误功能码名称 | 🆕 新增 |
| L-6 | Low | `docs/handoff_test.md` §1.2/§14/§15 | 测试计数漂移（24/25 vs 57） | 🆕 新增 |
| — | ✅ | v2.2 全部 1C+5M+7L | 历史缺陷复核通过，无回归 | ✅ 已闭环 |

---

## 十、审计师评估

1. **协议核心算法稳定**：CRC16/MODBUS、CRC8/0xE5、定义符、负数 BCD、帧结构、SL427 控制域/地址域/Tp 经 13 轮审计 + 48 条真实报文验证，未发现算法级错误。
2. **最严重缺陷（M-1）**：SL651 `FUNC_MAP` 功能码名称与规约正文、`project.md`、编码器方法三方矛盾，且被示例注释「互相印证」而长期漏检；影响所有解码输出的功能码名称语义。建议优先修复并补一条「编码→解码名称一致」回归测试。
3. **系统性盲区**：v2.2 解决了「要素数值」验证缺失，但「字段语义」验证仍缺失；同时变异测试以「仅抛受控 DecodeError」为通过标准，无法发现「合法输入被拒」（M-2）。建议为 fuzz 增加「合法帧不得抛异常」的正向用例。
4. **建议下一轮优先处理**：M-1（功能码名称，影响面最广）> M-2（0xAA 缺测鲁棒性）> M-3（人工置数契约）> M-4（长度校验）。
5. **方法论建议**：将 `FUNC_MAP` / `AFN_MAP` 逐项与规约正文建立对照表并纳入 Layer 1 常态核查；对每个编码器便捷方法补「数据域长度/边界」校验断言；示例报文注释应在修复后重新生成，避免「注释与缺陷实现互相印证」。

> 本报告只审不修，未修改任何源码、测试或文档；所有结论均可由报告内命令复现。
