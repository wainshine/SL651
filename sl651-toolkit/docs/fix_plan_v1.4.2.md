# SL651-Toolkit v1.4.2 修复方案（v2.7 审计 + 对抗复核）

> 状态：**已实施（WP-1~WP-6），v1.4.2 待验收**（v1.2 评审后修订，2026-11-03）
> 基线：v1.4.1，git `44535d6`；实施后 `python3 -B tests/run_all.py` → **11/11**
> 输入：
> - `audit/audit_report_v2.7.md`（2M+7L，已用 SL651/SL427 PDF 原件交叉复核）
> - `audit/audit_review_v2.7.md`（对抗复核：新增 M-2c、M-1 ASCII 计数修正）
> - SL651 报批稿 PDF 第 44~48 页（表 C.1）、第 76 页起（表 G.1）；SL427 PDF 第 11/14/24 页
> 目标版本：**v1.4.2**
> 原则：先修「表基线/长度解析」这两类根因，再修 ASCII/降级/文档；每项都要有可重放的失败用例。
> 实施进度：**WP-1~WP-6 已落地（2026-11-03）**；`run_all.py` 11/11。
> 本版修正（评审）：① `buf[14]`→`buf[13]`；② 16 位触点补 `_decode_binary`；③ legacy 保持 12 位；④ SBL 单位 m³/h；⑤ center 1~254；⑥ ASCII 目标 **130 字面键** + `DRxnn` 动态识别（非 131）；并按 PDF 裁决表22/表23 的 SYN 长度语义。

---

## 0. 结论摘要

1. v2.7 的 **M-1、M-2 主体成立**；对抗复核新增 **M-2c**：SL651 SYN **单包 16 位长度**被按 12 位解析，单包 >4095 直接 CRC 失败，比“重组后 >4095 丢弃”更前置。
2. M-1 的 ASCII 不是 3 处错码，而是 **4 处语义错配**（`SQ` 当前也被错安为“输沙量”）；且必须把 **表 C.1（规范性）** 与 **表 G.1（资料性，SL330 人工置数）** 拆成两张表，不能在一张表里改名。
3. M-2 必须拆成 M-2a（SL651 合计 >4095）、M-2b（SL427 合计 >255）、M-2c（SL651 单包 16 位长度）三项；仅改“合成单帧”不够。
4. 本方案共 **6 个工作包**：WP-1 表基线、WP-2 SL651 重组、WP-3 SL427 重组/B1、WP-4 ASCII 合规、WP-5 配置/文档、WP-6 发布。
5. 预估改动集中在 `sl651/constants.py`、`sl651/decoder.py`、`sl427/decoder.py`、`tools/simulate_cli.py`、测试与文档；不改协议核心 CRC/BCD。

---

## 1. 范围与定级

| 来源 | 项 | 级别 | 本方案处理 |
|---|---|---|---|
| v2.7 | M-1 要素表覆盖缺口 + ASCII 错码 | Medium | WP-1 |
| v2.7 | M-2 重组表达上限（a/b） | Medium | WP-2/WP-3 |
| 对抗复核 | M-2c SYN 单包 16 位长度 | Medium | WP-2 |
| v2.7 | L-1 ASCII 分类码 | Low | WP-4 |
| v2.7 | L-2 ASCII SYN 包号 | Low | WP-4 |
| v2.7 | L-3 decode() 直解 SYN 部分数据 | Low | WP-2 |
| v2.7 | L-4 0x26 文档 N(6,1) | Low | WP-5 |
| v2.7 | L-5 YAML center/password | Low | WP-5 |
| v2.7 | L-6 AFN=B1 无解析 | Low | WP-3 |
| v2.7 | L-7 AFN=84 超长截断 | Low | WP-3 |
| 对抗复核 | M-1 ASCII 4 处错配（含 SQ） | 并入 M-1 | WP-1 |
| 可选 | SA-R1 孤立 DIVS=1 反馈 | Low | WP-3（可选） |

---

## 2. WP-1 表基线：表 C.1 全量 + 表 G.1 独立（M-1）

### 2.1 目标

- `SL651_ELEMENTS`：覆盖表 C.1 的 **131 行**（F0~FD 14 行 + 01~75 117 行）+ 保留现有 **80H** 厂商自定义 = 目标 **132 键**。
- `SL651_ASCII_ELEMENTS`：只承载**规范性表 C.1** 的字面 ASCII 标识符，目标 **130 字面键**；04H 的 `DRxnn` 是模式码（x∈D/H/N），不登记为字面键，由 `_ascii_time_step_desc` 动态识别（保持 v1.3.1 L-3 的修复）。
- 新增 `SL651_ASCII_ELEMENTS_G`：承载**资料性表 G.1**（SL330 人工置数），默认不参与普通 ASCII 正文解析。
- `docs/project.md`/`README`/`sl651/README` 的“101 项已全部收录”改为实际口径。

### 2.2 具体补录/修正

**HEX/BCD 侧（SL651_ELEMENTS）**

- 58H~5FH：WP1~WP8 水压 1~8（N(5,2)，kPa；逐行：58H WP1、59H WP2、5AH WP3 … 5FH WP8）
- 60H~67H：SYL1~SYL8 水表剩余水量（N(11,3)，m³）
- 68H~6FH：SBL1~SBL8 水表每小时水量（N(10,2)，m³/h）
- 70H~72H：VTA/VTB/VTC 交流三相电压（N(4,1)，V）
- 73H~75H：VIA/VIB/VIC 交流三相电流（N(4,1)，A）
- FDH：DATA 流速批量数据传输（按附录 C 注 f；解析为原始字节/摘要，不做数值化）

**ASCII 侧（表 C.1，规范性）**

| 键 | 值 | 修正 |
|---|---|---|
| `NS` | 开机台数（19H） | 新增；删除 `MT` |
| `SW` | 输沙量（32H） | 修正当前“剩余水量” |
| `SQ` | 含沙量（44H） | **修正当前“输沙量”** |
| `ZT` | 遥测站状态及报警（45H） | 新增 |
| `SYL1`~`SYL8` | 水表剩余水量（60H~67H） | 新增 |
| `SBL1`~`SBL8` | 水表每小时水量（68H~6FH，m³/h） | 新增 |
| `WP3`~`WP8` | 水压 3~8（5AH~5FH） | 新增（`WP1/WP2` 已在表中） |
| `VTA/VTB/VTC` | 交流三相电压（70H~72H） | 新增 |
| `VIA/VIB/VIC` | 交流三相电流（73H~75H） | 新增 |
| `DATA` | 流速批量数据（FDH） | 新增 |
| `SD` | — | **删除**（仅表 G.1 有“日平均含沙量”） |

> 注意：不能按 v2.7 的字面“SD→SQ”直接改键；`SQ` 已存在且当前值也是错的，必须显式写成“删除 SD；SQ=含沙量；SW=输沙量；NS=开机台数”。

**表 G.1（资料性，SL330）**

- 新增独立映射：`SL651_ASCII_ELEMENTS_G`，保留 `SD=日平均含沙量`、`SQ=含沙量`、`SW=输沙量`、`NS=开机台数`、`SQS/SWD` 等 G 专有码。
- `SL651_ASCII_ELEMENTS` 不含 `SD/SQS/SWD`，避免两套体系混用。
- 0x35 人工置数的 F2 载荷：默认仍按原编码字节摘要显示；新增可选 `decode_manual_payload(payload, table="G")`（或等价 API），显式启用表 G.1 解析；普通 ASCII 正文 `build_ascii_body`/`_parse_ascii_elements` 只用表 C.1。
- 文档写明：表 C.1 规范性、表 G.1 资料性；两者不可合并。

### 2.3 一致性测试（新增 `tests/test_constants_spec.py`）

- 固化 `tests/fixtures/sl651_table_c1.tsv`：131 行，字段 `序号/引导符/ASCII码/名称/单位/数据定义/来源页码`，由 PDF 第 44~48 页提取（一次性脚本生成，测试不读 PDF）。
- 断言：
  - `SL651_ELEMENTS` 覆盖 131 行 + 80H（132 键）；键集、名称、单位、`N(x,y)` 定义逐行一致；
  - `SL651_ASCII_ELEMENTS` **130 字面键**；`NS/SW/SQ/ZT` 语义正确；`MT/SD` 不存在；04H `DRxnn` 由 `_ascii_time_step_desc` 动态识别（单独断言 `DRN05` 等）；
  - `SL651_ASCII_ELEMENTS_G` 与表 G.1 基线一致；
  - `project.md` 声明的计数与实际键数一致。
- 再固化 `tests/fixtures/sl651_table_g1.tsv`（表 G.1）；G 表不参与 C 表断言。

### 2.4 验收

- 解码 58H/60H/70H/75H/FDH 帧时名称/单位正确，不再“未知(58)”；
- ASCII 帧含 `K`、`SQ`、`SW`、`ZT` 等可正确按名解析；
- `SL651_ASCII_ELEMENTS` 为 130 字面键，`DRxnn` 不占键但可动态识别；
- `tests/test_constants_spec.py` 通过；`run_all` 11 套件；
- 文档中“101 项”改为实际口径：HEX/BCD **132 键**（表 C.1 131 行 + 80H 自定义）、ASCII **130 字面键 + DRxnn 动态**。

---

## 3. WP-2 SL651 SYN：16 位长度 + 分片集合直接解析（M-2a/M-2c/L-3）

### 3.1 M-2c：单包 16 位长度

> **评审修正**：`C.STX_OFFSET = 13`，不是 14；原稿 `buf[14]` 读到的是流水号首字节，必须改为 `buf[13]`。

- `_extract_frame` 在读取长度前看 `buf[C.STX_OFFSET]`（即 `buf[13]`）：
  - `== SYN(0x16)` 且 `buf[11]` 的 bit7 **为 0**（表22，M3 上行）：按 **16 位纯长度**读 `body_len = (buf[11] << 8) | buf[12]`，`total = 14 + body_len + 3`；
  - `== SYN(0x16)` 且 bit7 **为 1**（表23，下行 SYN，说明「见表20」）：按 `方向位(bit7) + 12 位长度` 读，`direction=1`，`total = 14 + body_len + 3`；
  - `== STX(0x02)`：维持 12 位长度 + 方向位；
  - **legacy 0101（旧双 SOH）保持 12 位长度**，不启用 16 位 SYN 语义。
- 同一判别必须同时落在 **四处**：
  1. `_extract_frame`（帧提取）；
  2. `_handle_syn`（缓存/重组）；
  3. `_find_valid_start`（谎报长度重同步）；
  4. `_decode_binary`（`syn_pad` 路径，`total==1` 的 SYN 单包会直接走 `decode()`；漏掉这里会让单包 >4095 错位）。
- `_handle_syn` 不再把 `frame[11]` 的 bit7 当上行方向位；上行 SYN 方向=0，下行 SYN 方向=1。
- `_max_frame_bytes` 从 4124 提高到 `14 + 65535 + 3 = 65552`；`_buf_max` 提高到至少 256KB；仍需保留上限保护。
- ASCII SYN（表18）仍按 12 位长度（表16 的 4 字符 = 方向 + 3 位长度），不要误改为 16 位。
- 表22 长度 ≥0x8000 时 bit7=1 会与“下行 SYN”判别歧义；按 H.4.2 建议单包 ≤256B，实际不可达，文档记录该理论歧义。

**测试**：手工按表22 拼 5003B 单包（3B 包头 + 5000B 正文）→ `feed()` 不再 CRC 失败；`decode()` 单包（total==1）同样正确；5000B 单包 + 后续包 → 进入重组。

### 3.2 M-2a：SL651 重组结果直接进解析管线

**SL651**：

- `_handle_syn` 不再 `_build_reassembled` + `decode`，改为 `_decode_reassembled_binary/ascii(first_header, combined_body, packet_count, per_packet_crc)`。
- 抽出 `_decode_binary`/`_decode_new_ascii` 的“报头元数据 + 正文解析”公共部分，供单帧和重组复用；`body_length` 使用逻辑合并长度（可 >4095），不再构造 12 位长度的合成帧。
- `_decode_binary` 的 `syn_pad` 分支必须与 `_extract_frame` 的 16 位/12 位判别同源（见 §3.1），否则 `decode()` 单包 >4095 仍会错位。
- `DecodedMessage` 增加/复用 `reassembled=True`、`packet_count=N`；`crc_ok` 由所有分包 CRC 决定；`hex_input`、`byte_map`、`frame_length` 的语义在文档中写明（建议 `hex_input` 为各包拼接、`frame_length` 为各包总字节）。
- `_build_reassembled` 可删除或仅保留为“小正文”兼容路径；建议删除，避免两套长度语义。

### 3.3 L-3：`decode()` 对 SYN 分包的安全降级

- `decode()`/`decode_hex()` 遇到 SYN 且 `total > 1`：返回 `elements=[]`、`reassembled=False`，`warnings=["SYN 分包帧（total=N, seq=M），请使用 feed() 重组；单帧不解析正文"]`；`crc_ok` 照旧；`total==1` 可正常解析。
- 实现细节：`_decode_binary` 的 `syn_pad` 路径当前只跳过 3B 包头，需**读取**其中的 `total/seq`（表22 高12位/低12位）才能判 `total>1`；该读取与 `_handle_syn` 共用同一解析函数，避免两处不一致。
- CLI/Web 的 `decode_hex()` 路径自然显示 warning；`feed()` 保持重组。
- 测试：`decode(1/3 包)` 空要素 + warning；`feed()` 仍重组。

### 3.4 验收

- 单包 5003B 可解析/进入重组；两包合计 5050B 不再报 `>4095`；
- `decode()` 不再静默输出部分要素；
- 现有 2/3 包、乱序、逐包 CRC、缓存上限测试全过。

---

## 4. WP-3 SL427 重组 + B1 + 84（M-2b/L-6/L-7）

### 4.1 M-2b 直接解析

- `_handle_div_frame` 收集 `{divs: frame}` 后，直接拼 D 并调用 `_parse_data_field`；不再 `_synthesize` 255B 上限。
- B0/B1/84 无 AUX；直接解析后构造 `DecodedMessage`，`data_len=len(payload)`（可 >255），`reassembled=True`。
- `decode()` 单帧 DIV 仍安全降级（既有行为不变）。

### 4.2 L-6 AFN=B1

- 增加 `afn_hex == "b1"` 分支：按 §7.3.23/表 B.75：
  - 前 9B：参数种类+编号、开始/结束时间（表48）→ 输出“参数种类/编号、开始时间、结束时间”；
  - 后续数据：**按控制域 `ctrl["func_code"]` 分派** 7.3.22 的对应参数类型解析（规约明确“命令与类型由控制域 C 决定”，不存在“无法确定类型”的合法分支）；
  - 只有分派后解析失败（数据不足/非法 BCD）才输出命名原始摘要 + warning，至少不再“未知功能码 AFN=0xB1”。
- 如果本轮无法完整解析某类参数，最低验收：B1 不再落兜底“未知功能码”，输出 AFN 名称 + 9B 头字段 + 已分派解析结果/原始摘要 + warning。
- 由于 B1 在 `_DIV_REASSEMBLE_AFNS`，测试需覆盖“B1 单帧 + B1 分帧重组后解析”。

### 4.3 L-7 AFN=84 超长

- `len(data_field) > 2`：`warnings.append("AFN=84H 数据域 X 字节（>2B），仅解析前 2B 电压")`，仍解析前 2B；`<2` 保持现有 warning。
- 测试 D=3B。

### 4.4 可选 SA-R1

- `SL427Decoder` 增只读 `pending_warnings`（或 `feed()` 返回诊断）以即时暴露孤立 DIVS=1；若本轮不做，保留现有 TTL warning。

---

## 5. WP-4 ASCII 合规（L-1/L-2）

### 5.1 L-1 ASCII 分类码

- `build_ascii_body`：`parts.append(chr(self.station_type))`；校验 `0x20 <= station_type <= 0x7E`，否则 `EncodeError`。
- `_extract_ascii_times`：
  - 单字符 ASCII（如 `K`）→ `ord(token)`；
  - 兼容旧 2 字符 HEX（如 `4B`）→ `int(token,16)` + warning（历史帧/厂商帧）；
  - 非两者 → `-1/未知`。
- 测试：`K` → 水库；`4B` 兼容 + warning；编码帧 ST 段为 `K`。

### 5.2 L-2 ASCII SYN 包号

- `_handle_syn` ASCII：
  - `total = int(pkt[0:3], 16)`；`seq = int(pkt[3:6], 16)`；
  - `try/except ValueError` → `DecodeError`；
  - 范围 1~4095。
- 测试：`00A001`（10 包）可解析；`009001` 兼容；非法 hex 报错。

---

## 6. WP-5 配置/文档（L-4/L-5）

### 6.1 L-4 0x26 文档

- `simulator/generators.py`、`simulator/rain_station.py`、`README.md`、`docs/handoff_main.md` 中 0x26 的 `N(5,1)` → `N(6,1)`；数值上限 99999.9mm、3B/1 位小数不变。
- 加一个 grep/文档断言或测试注释，避免再次回归。

### 6.2 L-5 YAML center/password

- `_validate_center(v)`：整数、**1~254**（与 `SL651Encoder.__init__` 的 `1 <= center_addr <= 254` 一致）；
- `_validate_password(v)`：整数、0~65535（与 `SL651Encoder` 的 `password` 校验一致）；
- `_load_config` 的 `engine.add_station` 捕获 `(EncodeError, ValueError, TypeError)`，输出 `stations[i] 配置错误: ...` 并 `return 1`；
- CLI 主路径同样处理；
- 测试：`center: "2"` / `password: "0"` → 可读错误，不裸栈。

---

## 7. WP-6 发布与测试

### 7.1 新增/扩展套件

| 套件 | 内容 |
|---|---|
| `tests/test_constants_spec.py`（新） | 表 C.1 131 行 + 80H；ASCII C.1；表 G.1 独立；文档计数 |
| `test_sl651_multipacket.py`（扩展） | 16 位单包 5003B；合计 5050B；`decode()` SYN 警告；ASCII SYN 10 包 |
| `test_sl427_multiframe.py`（扩展） | 307B 直接解析；B1 单帧/分帧；84 D=3B |
| `test_protocol_contracts.py`（扩展） | ASCII `K`；YAML center/password 字符串；0x26 文档断言（可选） |
| `run_all.py` | 10 → 11 套件 |

### 7.2 回归门禁

1. `python3 -B tests/run_all.py` → 11/11；
2. 福建 23 / 北京 25 → rc=0，要素级基线不变（新增 45H/58H 等不影响既有断言）；
3. 5003B 单包、5050B 组合、SL427 307B 组合不再报“超范围”；
4. `decode()` SYN 分包空要素 + warning；
5. 表 C.1/G.1 全量测试通过；
6. `compileall` + `git diff --check`。

### 7.3 版本/文档

- `__version__ = "1.4.2"`；
- `README` 版本历史、`docs/project.md` §2.3/§2.5/§3.2/§7、`handoff_main`/`handoff_test` 计数与说明；
- `audit/audit_report_v2.7.md` 由审计会话补 M-2c/PDF 复核结论；主会话不修改审计结论；
- `fix_report_v1.4.2.md` 记录闭环。

---

## 8. 实施顺序与检查点

```
P0  WP-1 表基线 + fixtures + 文档计数
P1  WP-2c SYN 16 位长度（先单独修，最小风险）
P2  WP-2a/WP-2b 重组直接解析（架构改动）
P3  WP-4 ASCII（分类码/包号）、WP-2 L-3
P4  WP-3 B1/84、WP-5 YAML/文档
P5  WP-6 版本/测试/发布
```

- **检查点 1（P1 后）**：5003B 单包不再 CRC 失败；现有测试全过。
- **检查点 2（P2 后）**：5050B/307B 重组直接解析成功；逐包 CRC/乱序/上限不回归。
- **检查点 3（P5 前）**：表 C.1/G.1 全量、ASCII、B1、YAML、真实语料全过。

---

## 9. 风险与待确认

1. **SYN 16 位长度的方向语义（已裁决）**：表22 为 M3 上行、16 位纯长度；表23 下行 SYN 引表20（方向位 + 12 位）。实现按 `buf[11]` bit7 判别：=1 下行 12 位，=0 上行 16 位；≥0x8000 的理论歧义按 H.4.2 实际不可达处理并文档化。
2. **直接解析的 API 语义**：`body_length` 可能 >4095/255，`frame_length`/`hex_input`/`crc_*` 的展示需文档化；保持 `DecodedMessage` 兼容，不新增必填字段。
3. **B1 数据域**：前 9B 头（表48：参数种类/编号 + 起止时间）可明确解析；后续数据按控制域 `ctrl["func_code"]` 分派 7.3.22 的参数格式，**不存在“无法确定类型”的合法分支**；只有分派后解析失败才落原始摘要 + warning。
4. **表 G.1**：只作为独立表，不做普通 ASCII 正文解析；0x35 F2 的 G 表解析设为可选。
5. **83/61 图片 L×1K**：仍按 v1.4.1 的保守策略，M-2 直接解析不改变该边界；待真实样本。
6. **版本**：M-2c 是 Medium 修复，建议 v1.4.2（patch/minor 语义按项目习惯；可讨论 1.5.0）。

---

## 10. 非目标

- 不在本轮实现完整 SL330 人工置数协议；
- 不改 CRC/BCD/定义符等核心算法；
- 不解决 83/61 L×1K、DIVS 255 读法、Mqttx paho、Web 脱敏等既有残余（除非 WP-3 可选 SA-R1 纳入）；
- 不修改历史审计报告的结论；PDF 复核结论由审计会话维护。
