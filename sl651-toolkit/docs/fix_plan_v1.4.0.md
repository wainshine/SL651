# SL651-Toolkit v1.4.0 修复方案（审计评审稿）

> 状态：**已实施（v1.4.0，2026-11-02）**；本文保留为评审/实施记录（v1.1 评审后修订）
> 基线：`v1.3.2`，git `5b02471`（2026-09-14），`python3 -B tests/run_all.py` → 8/8
> 输入报告：`audit_report_v2.5.md`（4M+11L）、`audit_report_v2.6.md`（1M+8L）、v2.6 补充审计（L-12~L-17 + 1 项潜伏观察）
> 目标版本：**v1.4.0**（新增 SL427 分帧重组 API，按项目历史属 minor 变更）
> 评审对象：审计 A（v2.5 复核 / L-12~L-17）、审计 B（v2.6）
> 评审文件：`audit/plan_review_v1.4.0.md`（审计 B）；审计 A 意见见对话记录
> 修订摘要：M-4 降为 Low 并修正 C0 0x0D 电压语义；Q2 保守方案升级为主方案；WP-2 增加 83/61 L×1K 与 DIVS 倒计数修订；WP-10 白名单收紧；A 补齐限定 40H~43H
> 原则：先修数据完整性，再修语义正确性，最后修契约/可观测性/文档；每一项都必须有“可重放的失败用例 → 修复后用例”。

---

## 0. 结论摘要

1. 待修项共 **30 项**（v2.5 15 + v2.6 9 + 补充 6），另有 **1 项潜伏观察**（当前无活跃触发路径）。全部仍在基线代码中，与“代码零改动”的复核一致。**评审后 v2.5 M-4 由 M 降为 L**，当前严重度口径为 **4M+26L**（M：v2.5 M-1/M-2/M-3 + v2.6 M-1）。
2. 去重后收敛为 **14 个工作包（WP-0 ~ WP-13）**。去重不取消发现，只合并同一根因/同一函数的修复与验收。
3. 必须先修的三项数据完整性缺陷：**v2.5 M-1（SYN 逐包 CRC/跨报文）**、**v2.5 M-3（feed 无界/无错误通道）**、**v2.6 M-1（SL427 DIV 分帧不重组）**。这三项不修，后续语义修复都建立在“可能返回错误数据”的底座上。
4. 新增 **2 个测试套件**（`test_sl427_multiframe.py`、`test_protocol_contracts.py`），扩展 5 个既有套件；`run_all.py` 由 8 套件变为 10 套件。
5. 版本定为 **v1.4.0**：SL427 `feed()` 与 `build_frame(divs=...)` 是新增能力；Q2 的保守重组（B0/B1/84）仍是新增 API，**不降级**；只有完全不做重组、仅安全降级时才降为 v1.3.3。
6. 本方案有 **7 个需要审计裁决的问题**（§3），其中 Q1（v2.5 M-4 的 0x0D 上下文）与 Q2（分帧 AUX 归属）直接影响修复口径，建议先裁决再进入对应 WP。
7. **评审后的实质变更**：① M-4 降为 Low（表 24 D12 表明 C0 的 0x0D 本是 2B 电压，报告复现的 4B 短帧是畸形帧）；② Q2 只对 B0/B1/84 重组，83/61 因 `L×1K` 语义未证而阻塞，C0/81/82 安全降级；③ DIVS 改为“DIVS==1 触发、降序拼接、缺号报错”；④ A 补齐只在 40H~43H 配置帧启用；⑤ WP-10 白名单收紧为 `{0x30,0x32,0x33}`。

---

## 1. 输入报告与基线

### 1.1 基线确认

| 项 | 结果 |
|---|---|
| 源码改动 | 无；`find sl651 sl427 simulator tools web -name '*.py' -newermt 2026-10-28` 为空 |
| 版本 | `sl651/__init__.py:__version__ = "1.3.2"` |
| 测试 | `python3 -B tests/run_all.py` → 8/8 |
| 审计文件 | `audit_report_v2.5.md`、`audit_report_v2.6.md` 均未入库（git `??`） |
| L-12~L-17 | 目前只在审计回话中，**尚未归档为报告文件**；建议由审计会话补 `audit_report_v2.6_addendum.md`（主会话不代写审计结论，见 §6.2） |
| 评审文件 | `audit/plan_review_v1.4.0.md`（审计 B，2026-11-02）；审计 A 裁决见对话记录 |

### 1.2 去重映射（30 项 → 14 WP）

| WP | 覆盖的发现 | 主题 |
|---|---|---|
| WP-0 | v2.5 L-4、L-6；补充 L-14 | 共享异常类、SL427 `_warnings` 实例状态、死导入 |
| WP-1 | v2.5 M-1、M-3、L-2、L-11 | SL651 SYN 逐包 CRC、跨报文、`feed()` 上限/错误通道/重同步、旧方言 ASCII |
| WP-2 | v2.6 M-1 | SL427 DIV=1 分帧重组（仅 B0/B1/84）、单帧安全降级、编码侧 DIVS；83/61 的 L 语义阻塞 |
| WP-3 | v2.5 M-2、L-1；v2.6 L-8；潜伏观察 | 填充语义、综合参数定长块、信道 0xFF、`_safe_hex_val` |
| WP-4 | v2.5 M-4（降 L） | 0x0D 上下文：B0/C0 电压语义保持，81 无中间参数，短帧/异常 D 长度降级 |
| WP-5 | v2.6 L-6；补充 L-15 | 45H 状态数据位宽与文档矛盾 |
| WP-6 | v2.5 L-9、L-10；v2.6 L-2；补充 L-13 | 编码器入口校验与异常契约（guide/NaN/inf/direction/年份/mode/heartbeat） |
| WP-7 | v2.5 L-3；v2.6 L-1、L-3、L-5；补充 L-17 | 小时报数组边界、地址方式往返、A 补齐 BCD、F5 定义符 |
| WP-8 | v2.5 L-7；v2.6 L-4；补充 L-12 | CLI 脱敏：中心站地址、原始报文、errors 路径 |
| WP-9 | v2.6 L-7 | TcpSender 持锁 `sleep(1)` |
| WP-10 | v2.5 L-5 | YAML `function_code`/`alert_threshold` 校验与装载期报错 |
| WP-11 | 补充 L-16 | 雨量站 0x1F 与 0x20 恒相等 |
| WP-12 | v2.5 L-8 | MqttxSender 每报文一进程 + 密码 argv 暴露面 |
| WP-13 | 补充 L-14、潜伏观察、全部文档/版本/测试计数 | 收尾与发布 |

> 注：v2.6 L-2 与补充 L-13 都涉及 `build_set_work_mode`，合并到 WP-6；v2.6 L-6 与补充 L-15 同指 45H 文档矛盾，合并到 WP-5；v2.5 L-3 与 v2.6 L-3 是同一函数的上限/下限两个方向，合并到 WP-7 但保留两个独立用例；其中 AFN=84 报错文案属 WP-6，F4 docstring 属 WP-7。**v2.5 M-4 经评审降为 L，但 WP 编号保留（WP-4），便于与报告对照。**

---

## 2. 全局修复契约（先立规矩，再动代码）

以下 6 条建议写入 `project.md` 的新章节“§2.7 健壮性契约”，并作为本轮每个 WP 的验收前提：

- **C1 不静默降级**：凡工具无法正确解析/编码的输入，必须二选一——抛 `EncodeError`/`DecodeError`，或产出 `-`/原始摘要并写入 `warnings`。禁止“空输出、错位输出、吞字节”三型静默行为。
- **C2 同源判定单点实现**：填充判定、地址方式判定、0x0D 上下文、A 补齐判定，各只能有一个函数/常量表；编解码两侧必须共用，禁止两边各写一套前置条件。
- **C3 校验值不得遮蔽原始校验**：合成分帧/重组帧可以重算 CRC，但必须同时保留“逐包/逐分片原始校验结果”；任一原始校验失败，不得输出 `crc_ok=True`。
- **C4 状态机三要素**：所有多包/分帧状态机必须定义**超时、上限、重置条件**；规约没给的，实现补默认值并文档化。
- **C5 异常契约统一**：`sl651` 与 `sl427` 的 `EncodeError`/`DecodeError` 必须是同一组类；公开编码方法不得泄漏 `ValueError`/`TypeError`/`OverflowError`。
- **C6 API 兼容**：已有公开方法签名不变；新增能力用可选参数/新方法（`feed()`、`divs=`、`a_pad_guides=`、`--show-raw`）；默认行为的安全化变更必须在 README 版本历史中标注。

---

## 3. 7 个裁决点（已按审计 A/B 意见修订）

### Q1（评审后修订）v2.5 M-4 降为 Low：0x0D 的“电压”在 B0/C0 上本是合法语义

**结论：M-4 的 Medium 分级不成立，降为 Low；WP-4 保留，但改为“注释纠正 + 短帧/异常长度降级”。**

**证据 1（B0，无争议）**：§7.3.22 n) 明确查询输入电压响应数据域 2+4、类型码 1101B；表 B.73 无 Tp。B0 + 0x0D = 2B 电压 + 4B alarm/state，当前解析正确（实测 `60 12` → 12.60V）。

**证据 2（C0，报告与两次评审都未覆盖）**：表 24“数据自报种类”D12 的规范名是 **“报警或状态(监测终端机电压)”**（规约行 873）。按表 24 D12 推断，C0 + 0x0D 的参数数据 D 应为 **2B 电压**（该推断请审计确认），其后才是 2B alarm + 2B state + 7B Tp。实测 13B 数据域（`60 12` + alarm + state + Tp）当前代码输出 `电压=12.60` + 完整 alarm/state + 观测时间，**完全正确**。

**证据 3（v2.5 M-4 的复现）**：报告原文的数据域是“报警状态 2B + 终端状态 2B”共 4B，且明确“终端状态 2B 被丢弃”，说明它没有 Tp，走的是 `raw_len < 11` 的短帧降级分支。实测 4B 短帧 → `电压=0.01` + warning；这是**畸形帧容错**，不是“规约合法输入被误解”。

**证据 4（审计 B 的 15B 复现）**：D=4B + alarm + state + Tp 是足额长帧，但 0x0D 的 D 按表 24 应为 2B 电压；4B D 会把后 2B 静默丢弃（实测输出 `电压=0.01` + 完整 alarm/state）。它同样是**非标准 D 长度**，但暴露了一个真实缺口：D 长度不等于 2B 时没有 warning。

**因此**：

- M-4 从 Medium 降为 **Low**（命名/注释误导 + 短帧/异常长度降级不完整）；不按“合法输入误解”排期。
- 上下文矩阵修正为下表（这是对审计 A“4B 短帧”和审计 B“15B 长帧”两种复现的统一解释）：

| AFN | 0x0D 的合法布局 | 解析口径 |
|---|---|---|
| B0 | 2B 电压 + 4B alarm/state | 电压（保持） |
| C0 | **2B 电压** + 2B alarm + 2B state + 7B Tp | 电压 + alarm/state（保持）；D≠2B → 原始摘要 + warning |
| 81 | 2B alarm + **0B D** + 2B state + 7B Tp | 不解析电压；D 非空 → 原始摘要 + warning |
| 82 | 按 7.5.3 参照 7.3.22；0x0D 为 2B 电压 | 2B → 电压；其他 → 原始摘要 + warning |
| 84 | 2B 电压，无 AUX | 电压（专用分支） |
| 短 C0/81（<11B） | 畸形 | 4B → alarm/state；其他 → 原始摘要；不输出假电压 |

**测试**：B0 `60 12` → 12.60V；C0 13B 合法帧 → 12.60V + alarm/state/time；C0 4B 短帧 → alarm/state + warning（无电压）；C0 15B D=4B → 不输出电压，D 原文 + warning，alarm/state 仍正确；81 0x0D 空 D → 仅 alarm/state；81 0x0D 带 D → 原文 + warning；84 不变。

> 这一修订比两位审计的 Q1 更进一步：审计 A 认为 C0 应降级为报警/状态、审计 B 认为 15B 长帧仍误解；按表 24 D12 的规范名，最合理的解释是 **C0 的 0x0D 为 2B 电压**；两者复现的 C0 帧 D 长度都不标准（请审计再确认）。WP-4 的实现设计因此从“C0/81/82 一律不解析电压”改为上表。

### Q2（评审后修订）分帧保守方案升级为主方案：仅无 AUX 且 L 语义明确的 AFN 重组

**结论：采纳审计 A/B 的保守意见；“Tp 只在末帧”不再作为实现依据，只作为待验证假设。**

- 规约唯一明确分帧的场景是图片（§7.3.17c）；表 B.63/B.96 图片帧无 PW/Tp；表 B.73（B0）、B.75（B1）无 Tp；C0/81/82 的分帧从未被规约描述。
- **主方案**：只对 **B0、B1、84**（无 AUX、L 语义按表 3 字节）启用 DIV 重组；**83/61 暂不重组**（原因见下），C0/81/82/FF 的 DIV 帧安全降级 + warning。
- **83/61 的 L 语义风险**：§6.3.3.2 b)「图片数据流的字节总数为 L×1K」与表 3「L=用户数据区字节数」冲突；若 L 是 1K 块数，`total=L+5` 会系统性算错。开工前必须找真实 83 样本核验；核验不了就让 83/61 走保守降级，MF-3 不作为通过用例。
- **DIVS 组装规则**：不再要求 `N==len(cache)`（若 DIVS 从 255 起倒计，N 未知）。改为：**DIVS==1 触发组装；按 DIVS 降序拼接；max DIVS 到 1 之间有缺号 → error，不输出**。缺失“最大号首片”无法从协议层发现，文档化残余风险。
- **divs==1 自含帧**：默认不把孤立 DIVS=1 当单帧（无法区分“单帧 DIV”与“多帧末片”，避免末片/坏 CRC 场景产垃圾）；仅 `SL427Decoder(allow_single_div=True)` 显式开启时解析 + warning。`decode()` 始终安全降级。MF-8 拆成 MF-8a（decode 降级）与 MF-8b（feed opt-in 单帧解析 + warning）。
- 编码侧 `divs=` 参数保留；不因保守方案降版本（新增 feed/divs 仍是 v1.4.0）。

### Q3 跨报文混组的残余风险能否接受“可观测 + 有界”，而非“完全消除”？

SL651 多包报文的 SYN 包头只有“包总数/序列号”，**没有报文标识**。因此“A 的 seq1/seq2 缓存 + B 的 seq3”在协议层无法 100% 区分。v2.5 M-1 建议的 seq==1 重置 + 超时淘汰只能降低概率，不能根除。

**本方案**：逐包 CRC 校验（坏包不进缓存）+ seq==1 重置 + 总包数变化重置 + **同一 seq 再次到达但内容不同 → 重置该组 + warning** + 组级 TTL + 组数/字节上限 + `reassembled/packet_count` 字段 + 异常时 warning；文档明确“无报文 ID，极端丢包+交错仍可能混组”。审计 A/B 均认为“同批次严格模式”会牺牲跨批次流式能力，不采纳；残余风险文档化。

### Q4 A 补齐 BCD 的适用范围：通用解码还是仅配置参数？

规约 6.6.3.3 b) 只对“遥测站目的地地址（如短信接收号码等，且不可能是负数）”规定奇数位用 `A` 补最高位。当前 `SL651_ELEMENTS` 是**要素表**（附录C），配置参数（附录D）没有独立映射；同一个引导符在 C/D 两张表里语义不同（如 0x05）。

**本方案的最小闭环**：

- 底层：`bcd_bytes_to_int(..., allow_a_pad=False)` / `int_to_bcd_bytes_a()`；只允许**最高半字节**为 A，其余仍必须是合法 BCD。
- 解码：`_safe_bcd_val` 增加 `allow_a_pad` 参数；**仅 40H~43H 配置帧解析路径启用**（附录D 参数所属域），`_parse_elements` 对“首半字节 A 且其余合法”的 BCD 值按 A 补齐解析并写 warning；定时报/普通要素路径保持拒绝（`-`），避免把普通畸形数据按地址语义解读。
- 编码：`build_set_param_body(..., a_pad_guides=set())` 显式指定哪些引导符按 A 补齐，**不按引导符自动猜**；新增 `build_set_param_body_a_padded` 或参数。
- 附录D 参数名的完整映射不在本轮范围（列入 P4 Roadmap）；本轮只保证“短信号码类值的 A 补齐编解码”可用、可观测。

### Q5 CLI 脱敏的默认行为：默认全遮 + `--show-raw`，还是仅 JSON 遮？

v2.5 L-7、v2.6 L-4、补充 L-12 指向同一件事：当前 text/JSON 都回显完整原始报文，且 `center_addr[:2] + "**"` 对 1 字节地址是**假脱敏**（`[:2]` 恒等，输出 `25**` 全显 + 装饰星号）。本方案建议：

- 默认（text + JSON）：中心站址 `**`；遥测站址保留前 2 个 HEX 字符 + `********`；密码 `****`；原始报文只显示 `7E7E…（N 字节，func=0xXX，已脱敏）`；`errors[].message` 不回显完整输入。
- 新增 `--show-raw`（仅本地调试）打印完整 hex；默认关闭。
- 这会改变现有 `test_cli_json_masking` 的断言（它只检查 `endswith("**")`，掩盖了 center 未脱敏的问题），需同步更新。

请审计确认“默认关闭原始报文”是否影响排障流程；若不可接受，退而求其次：text 默认保留原始报文、JSON/errors 默认脱敏，并加 `--mask-raw` 选项。

### Q6 MqttxSender：文档标注，还是引入 paho-mqtt 长连接？

v2.5 L-8 是 Low：每报文 spawn 一个 `mqttx pub` 子进程，且密码经 argv 传递（`ps` 可见）。彻底修复需要引入 `paho-mqtt` 长连接（新增依赖、重连/线程模型、测试桩），属于 v1.5 级别的改动。

**本方案建议 v1.4.0 只做**：README/simulator README 明确“密码可能出现在进程列表”的安全边界；代码在密码非空时输出一条一次性 warning；把“可选 paho-mqtt Sender”列入 P4 Roadmap。若审计要求本轮闭环，则改为可选依赖：检测到 `paho-mqtt` 时用长连接，否则回退 mqttx。

### Q7 版本与默认值变更：v1.4.0 + 三处默认行为变化，是否接受？

- `__version__` 1.3.2 → **1.4.0**；
- `encode_address()` 默认 `admin_code=0`（产出首字节 00H，被自家解码器判为方式2）→ 改为合法方式1默认（建议 `110000`），并校验 `110000 ≤ admin_code ≤ 829999`（GB/T 2260 省级码范围）；这是**行为变更**；
- CLI 默认脱敏（Q5）、`set_work_mode`/`heartbeat` 从“静默掩码”改为 `EncodeError`（调用方若依赖旧的宽容行为会感知到）。

请审计确认默认值/严格校验的边界；若担心破坏兼容，可把后两项放到 `strict=True` 可选参数，但这样又回到“默认静默”的老问题，本方案不推荐。

### 评审意见响应（2026-11-02）

| 评审项 | 审计意见 | 处置 |
|---|---|---|
| Q1 / 审计 A | M-4 应降为 Low（4B 短帧是畸形输入） | **采纳**；并进一步核验表 24 D12，确认 C0 的 0x0D 本是 2B 电压（13B 合法帧当前解析正确） |
| Q1 / 审计 B | 报告复现是 15B 足额长帧，方案定性需改 | **部分不成立**：v2.5 报告原文为 4B（终端状态被丢弃），审计 B 的 15B 是另构造且 D=4B 不符表 24；两种帧都加回归用例 |
| Q2 / 审计 A+B | 保守方案升级主方案；83/61 L×1K 风险；DIVS 倒计数规则；divs==1 细化 | **全部采纳**，WP-2 已按此重写 |
| Q3 / 审计 A+B | 不加同批次严格模式；同 seq 不同内容重置 | **采纳** |
| Q4 / 审计 B | A 补齐仅 40H~43H 配置帧 | **采纳** |
| Q5 / 审计 B | “空操作”改为“假脱敏”；保留帧长/功能码 | **采纳** |
| WP-1 / 审计 B | ASCII SYN 也要校验 4 字符 CRC | **采纳** |
| WP-10 / 审计 B | 白名单从 5 个收紧为 3 个 | **采纳** |
| 测试规约 / 审计 B | 分帧/多包用例必须按规约手拼，不得只用项目构造器 | **采纳**，写入 §5.3 |

---

## 4. 工作包设计

> 规模：S ≈ 0.5 天，M ≈ 1 天，L ≈ 2~3 天（仅相对估算，不含审计往返）。

### WP-0 基础：共享异常、warnings 去实例状态、死导入（规模 M）

**覆盖**：v2.5 L-4、L-6；补充 L-14。

**现状/根因**

- `sl651/encoder.py:15`、`sl427/encoder.py:15` 各自定义 `EncodeError`；`sl651/decoder.py:99`、`sl427/decoder.py:22` 各自定义 `DecodeError`。跨包 `except` 不生效。
- `sl427/decoder.py:843` 用 `self._warnings` 保存解析告警，`decode()` 名义无状态、实际有隐藏可变状态；共享实例跨线程会串告警。
- `sl651/decoder.py:14` 导入 `safe_bcd_to_int` 但全文未用。

**修复设计**

1. 新建 `sl651/errors.py`：
   ```python
   class ProtocolError(Exception): ...
   class EncodeError(ProtocolError): ...
   class DecodeError(ProtocolError): ...
   ```
2. `sl651/encoder.py`、`sl651/decoder.py`、`sl427/encoder.py`、`sl427/decoder.py` 改为 `from sl651.errors import ...`（保留模块级别名，旧导入路径仍可用）。
3. `sl651/__init__.py`/`sl427/__init__.py` 导出 `ProtocolError`（新增），`EncodeError`/`DecodeError` 指向同一对象。
4. `SL427Decoder._decode_inner` 创建局部 `warnings: list[str]`，传给 `_parse_data_field(..., warnings)`；删除 `self._warnings` 及 4 处 `self._warnings.append`。
5. 删除 `safe_bcd_to_int` 未使用导入；如后续 A 补齐需要，再从 `bcd` 显式导入。

**测试**

- `sl651.encoder.EncodeError is sl427.encoder.EncodeError is sl651.errors.EncodeError`；`DecodeError` 同理。
- 两个线程各自 `SL427Decoder`（共享实例）并发解码不同填充帧，断言 warnings 不串。
- `python -c "from sl651.decoder import DecodeError"` 等旧路径仍可用。

**验收**：C5 成立；`grep -n "_warnings" sl427/decoder.py` 为空；全套件通过。

---

### WP-1 SL651 SYN 多包与 `feed()` 状态机（规模 L）

**覆盖**：v2.5 M-1、M-3、L-2、L-11。

**现状/根因**

- `_handle_syn`（`sl651/decoder.py:347`）把 `body_slice` 直接入缓存，**从未校验逐包 CRC**；`_build_reassembled` 重算 CRC，导致 `decode()` 校验恒真。
- `_pending`/`_pending_meta` 无时间戳、无组数/字节上限、无 TTL；`seq` 无重置启发。
- `feed()` 的循环在 `frame is None` 且 `consumed>0` 时 `break`，前导垃圾丢弃后不重扫（L-11）。
- `_extract_frame` 把所有 `SOH` 当新 ASCII；旧方言 `0101` 在 `decode()` 可解、`feed()` 无法提取（L-2），且坏帧头每次只排空 1 字节。

**修复设计**

1. **状态与上限**（新增实例属性，文档化）：
   - `_pending_max_groups = 64`
   - `_pending_max_bytes = 8 * 1024 * 1024`
   - `_pending_ttl = 300.0` 秒
   - `_max_frame_bytes`：二进制 `14 + 4095 + 3 = 4112`；新 ASCII `24 + 4095 + 1 + 4 = 4124`
   - `_buf_max = 64 * 1024`
   - `errors: list[str]`（上限 100）、`dropped_frames: int`
2. **逐包 CRC**：`_handle_syn` 入缓存前校验本包 CRC——二进制/旧方言用 `crc16(frame[:-2])` 与 `frame[-2:]` 比对；**新 ASCII SYN 帧用末尾 4 个 ASCII 字符 CRC**（`frame[-4:]` 解析为 int 与 `crc16(frame[:-4])` 比对）；失败则不入缓存、`dropped_frames += 1`、写 error。只有全部包校验通过才可能重组。
3. **序列重置启发**：`seq == 1` 且该 key 已有缓存（且有 seq>1）→ 视为新序列重置；`total` 变化 → 重置；组级 TTL 超时 → 淘汰；组数/字节超限 → 淘汰最旧组。
4. **ETB/ETX 校验**：`seq < total` 期望 ETB、`seq == total` 期望 ETX；不符写 warning（不直接拒绝，兼容厂商差异），并记入合成消息。
5. **重组结果**：`_build_reassembled` 仅作为“让 `decode()` 可复用”的实现细节；合成后设置 `DecodedMessage.reassembled=True`、`packet_count=total`；若任一分包 CRC 失败（理论上不会入缓存），强制 `crc_ok=False` + warning。`DecodedMessage` 新增两个可选字段，`to_dict()` 增加同名键（向后兼容）。
6. **`_extract_frame` 重同步**：
   - 识别 `7E7E`（二进制）、`SOH SOH`（旧方言，按二进制长度域）、单 `SOH`（新 ASCII）三类；
   - 新 ASCII 帧头非法 → 跳到下一个起始符（而不是固定 1 字节），返回 `(None, consumed)`；
   - 若 `total` 超过 `_max_frame_bytes` 或缓冲超过 `_buf_max` 仍不完整 → 丢弃当前起始符并重同步，记 error；
   - `feed()` 中 `frame is None` 且 `consumed > 0` → `continue`（重扫），不再 `break`；`consumed == 0` 才等待。
7. **错误通道**：`feed()` 捕获 `DecodeError` 时写 `errors`（含帧长/原因，不含完整报文），保持返回列表不变；`reset()` 清空缓冲/缓存/错误。
8. **兼容**：`feed()` 返回类型不变；新增属性不影响旧调用。

**测试**（扩展 `tests/test_sl651_multipacket.py`）

- 误码包：翻转包 1 一个比特 + 正常包 2 → **不得**产出 `crc_ok=True` 的报文；应无输出或 `crc_ok=False` + error。
- ASCII SYN 包：翻转末尾 4 字符 CRC 之一 → 不入缓存、error 可见（评审补充）。
- 跨报文：A.seq1/A.seq2 后 B.seq1（total=3）→ 断言重置后按 B 重组；A1+A2+B3（无 B1/B2）→ 文档化残余风险，测试断言“至少带 `reassembled` 标记且不声称完全可信”，或按 Q3 裁决加严格模式。
- 3000 帧“仅 seq=1、total=4095、站址递增” → `len(_pending) <= 64`，缓存字节 ≤ 8MB，无内存线性增长。
- 少报/谎报长度 + 好帧同批 → 好帧在同一次 `feed()` 解出；坏帧进 errors。
- 前导 4B 垃圾 + 合法帧同批 → 本次解出 1 条（L-11）。
- 旧方言 `build_frame(ascii_mode=True)` → `feed()` 可解（L-2）。
- 增量/乱序/重复包/ETB-ETX 标记异常。

**验收**：审计 v2.5 M-1/M-3 的复现脚本全部不再产出错误值；`run_all.py` 多包套件全过；无 `crc_ok=True` 的误码重组。

**残余风险**：见 Q3；文档写明“协议无报文 ID，极端交错仍可能混组，已用 seq1/TTL/上限降低概率”。

---

### WP-2 SL427 分帧（DIV=1）重组（规模 L，开工前需修订）

**覆盖**：v2.6 M-1。

**现状/根因**

- `sl427/decoder.py:830-837` 对 `ctrl["div"]==1` 只 `offset += 1` 跳过 DIVS，随后把每个分片当完整报文解析；B0 末帧把“数据残片 + alarm”错位拼成 2B 位图，C0 分片把局部数据尾部当 Tp/alarm/state。
- `build_frame`（`sl427/encoder.py:94`）没有 DIVS 参数，`make_ctrl(div=1)` 产出的帧与解码侧布局不对称。

**修复设计（评审后修订）**

1. **单帧 `decode()` 安全降级**：
   - `div == 1` 且 `divs > 1`：不解析数据域，返回 `DecodedMessage(elements=[], warnings=["分帧报文（DIV=1, DIVS=0xNN）需多帧重组；单帧解码不解析数据域"])`，保留 CRC/地址/AFN/字节图。
   - `div == 1` 且 `divs == 1`：`decode()` 仍安全降级（无法区分单帧 DIV 与多帧末片）；`feed()` 默认保留待确认，`allow_single_div=True` 时按单帧解析 + warning（MF-8b）。孤立 DIVS=1 默认不解析，避免前序坏片/丢片时产垃圾。
2. **`SL427Decoder.feed()` 重组**（新增）：
   - 新增 `__init__`：`_buf`、`_pending`、`_pending_meta`、`errors`、`dropped_frames`；上限 64 组 / 8MB / TTL 300s。
   - `_extract_frame`：扫描 `68 L 68 … 16`；普通 AFN 用 `total = L + 5`；**重组 allowlist 仅 B0/B1/84**。83/61 因 L×1K 语义未证，`feed()` 不承诺支持（安全抛 `DecodeError`）且不重组；C0/81/82/FF 单帧 `decode()` 安全降级，不重组。
   - 逐帧 CRC8：覆盖用户区 `frame[3:-2]`；坏帧不入缓存、记 error。
   - 分组 key：`(dir, addr_bytes, afn, func_code)`；缓存 `{divs: frame}`；DIVS 为 1 表示末帧。
   - 组装：**DIVS==1 触发**；按 DIVS 降序拼接；max DIVS 到 1 缺号 → error、不输出；只取各帧数据域，B0/B1 无 AUX，末帧若有 Tp 按 Q2 待验证假设记录（B0/B1 实际上无 Tp）。
   - 合成帧：C 清除 DIV 位（1B）、A、AFN、拼接 D、重算 L/CS；调用 `decode()`；设置 `reassembled=True`、`packet_count=N`，并写 warning“多帧重组，协议无报文 ID，存在混组残余风险”。
   - 上限/TTL/重置：组数 64、字节 8MB、TTL 300s；同一 key 出现“1 后又出现更大 DIVS”视为新序列（清缓存 + warning）。
3. **编码侧对称**：
   - `build_frame(..., divs: int | None = None)`；`divs` 非空时校验 `1..255`，控制域 C 追加 DIVS 字节（共 2B），并要求 `ctrl_word` 已带 DIV 位（否则 `EncodeError`，避免隐式改控制字）。
   - 文档/示例：`build_frame(0xB0, make_ctrl(1,0,div=1), data, divs=2, ...)`。
4. **`DecodedMessage`** 增加 `reassembled: bool = False`、`packet_count: int = 0`；`to_dict()` 增加同名键。

**开工前阻塞项**

- 找真实 AFN=83/61 样本核验 `L×1K`；没有样本前，MF-3 标“L 语义待确认”，83/61 只做安全降级。
- 用真实/按规约手工拼的 B0/B1 分帧样本验证，不得只用 `build_frame` 自构造（避免自洽循环）。

**测试**（新增 `tests/test_sl427_multiframe.py`）

- B0 两帧（DIVS=2/1）重组结果与完整单帧 `elements` 逐字段一致（含 alarm/state）。
- B1 两帧重组；84 单帧/分片边界。
- 缺帧/缺号 → 无要素、errors 有记录、不产生垃圾告警。
- 乱序（2,3,1 同批）可重组；跨批次 2 后 1 可重组。
- CRC 坏的分片 → 整组不输出，不声称 `crc_ok=True`。
- `decode()` DIV=1/divs>1 → 空要素 + warning；`decode()` divs==1 → 空要素 + warning；`feed()` 默认不解析孤立 DIVS=1，`allow_single_div=True` 时解析 + warning（MF-8a/b）。
- 编码 `divs=2/1` → `feed()` 还原；`build_frame` 带 DIV 位但无 `divs` → `EncodeError`。
- 组数/字节/TTL 上限。
- **83/61 的 L 语义用例暂不作为通过项**，标记“待真实样本”。

**验收**：审计 v2.6 M-1 的三组复现全部不再产出垃圾；B0/B1 重组与单帧一致；`decode()` 永不把 `divs>1` 分片当完整报文；Q2 的 83/61 阻塞项有明确结论（样本或降级）。

---

### WP-3 填充语义、综合参数定长块、信道填充（规模 M）

**覆盖**：v2.5 M-2、L-1；v2.6 L-8；潜伏观察。

**现状/根因**

- `_parse_ctrl_func_data`（`sl427/decoder.py:81`）对非 array 填充块 `break`（静默省略），对 array 填充块 `continue`（跳过）；综合参数 `_parse_comprehensive` 用 `max_items=1` 复用该函数，填充块会“吃掉”下一参数的数据块。
- `_parse_channel_427` 只把 `0xAA` 降级为“无”，`0xFF` 输出 `'0xFF '`。
- `_safe_hex_val` 的“全 F → `-`”会误伤合法 HEX 值 `0xFF`，但当前 `dt=="Hex"` 仅 F2/F3（特殊分支）与 `80`（实际走 BCD），无活跃路径。

**修复设计**

1. 统一填充判定：保留 `_is_fill`（全 `0xAA` 或全 `0xFF`），`_parse_flow` 也改用它（当前只判 `0xAA`）。
2. `_parse_ctrl_func_data(..., layout="stream"|"fixed")`：
   - `layout="stream"`（B0/C0/81/82 的普通数据）：非 array 块填充 → 输出一个 `-` 要素（同名/同单位/raw=填充）并结束；array 块填充 → 输出 `-` 要素并继续（保留数组位置），只写一次 warning。
   - `layout="fixed"`（综合参数）：按 `item_len` 精确切块，**无条件** `offset += item_len`；块填充 → `-` + warning；块不足 → warning 并停止；绝不委托“跳过填充找下一个值”的数组语义。
3. `_parse_comprehensive`：去掉 `max_items=1` 的委托，改为 `_parse_fixed_block(func, chunk)`；每个置位 bit 恰好消费 `byteLen`，断言相邻参数 raw 不同。
4. `_parse_channel_427`：`t in (0xAA, 0xFF)` 且下一字节同为填充 → “无”；单字节填充 → “-” + warning；地址段填充 → “-”。
5. `_safe_hex_val`：加注释说明“当前无活跃路径；若未来新增 Hex 型要素，需区分非法标记 FF 与合法 0xFF”，并在 WP-13 文档记一笔；本轮不改行为（避免影响 F2/F3）。

**测试**

- 审计 M-2 复现：bit5 流量块 `AA×5`、bit6 水位、bit7 雨量 → 流量 `-`，水位/雨量值正确且 raw 互不相同。
- 标量填充（func=0x01 雨量 `AA×3`）→ 产出 `-`，不再静默消失。
- array 填充在中间/末尾 → 对应位置 `-`，长度保持。
- AFN=65 备信道 `0xFF` → “无”，`0xAA` → “无”，单字节 `0xFF` → “-” + warning。
- 综合参数短数据 → warning，不抛异常。

**验收**：v2.5 M-2/L-1、v2.6 L-8 的复现脚本结果符合预期；`test_fuzz_decoders` 的“填充必须降级 `-`”正向断言扩展后仍通过。

---

### WP-4 0x0D 上下文（规模 S，M-4 降为 Low）

**覆盖**：v2.5 M-4（降级后）。

**评审后修订**：M-4 不是“合法输入被误解”的 Medium。按表 24 D12“报警或状态(监测终端机电压)”：
- B0 0x0D = 2B 电压 + 4B alarm/state，正确；
- C0 0x0D = 2B 电压 + 2B alarm + 2B state + 7B Tp，当前实现正确；
- v2.5 的 4B 短帧是畸形帧（无 Tp），走短帧降级误出电压；审计 B 的 15B D=4B 也是非标准 D 长度，D 后 2B 被丢弃。
因此 WP-4 降为“注释纠正 + 短帧/异常长度降级”，不改变 B0/C0 的电压语义。

**修复设计**

- `CTRL_FUNC_MAP[0x0D]` 注释改为：“上下文相关：B0 查询输入电压=2B 电压；C0 自报=2B 电压 + alarm/state + Tp（表24 D12）；81=报警/状态，无中间参数；AFN=84=2B 电压。”名称可保留“电压/报警状态”。
- C0/82 分支：`func_code == 0x0D` 且 `len(real_data) == 2` → 按 2B 电压解析（保持）；`len(real_data) != 2` → 输出“报警参数原始摘要” + warning，不解析电压；短帧（`raw_len < TP_LEN + 4`）4B → `_parse_alarm`/`_parse_terminal`，其他 → 原始摘要 + warning。
- 81 分支：`func_code == 0x0D` 时 `real_data` 应为空；非空 → 原始摘要 + warning，不解析电压。
- B0 分支：保持 2B 电压；`real_data` 非 2B → 原始摘要 + warning（不静默丢弃）。
- 84 专用分支不动。

**测试**

- C0 13B 合法帧（`60 12` + alarm + state + Tp）→ 12.60V + alarm/state/time（回归，防止误改）。
- C0 4B 短帧 → alarm/state + warning，无电压。
- C0 15B（D=4B）→ 无电压、D 原文 + warning、alarm/state 正确。
- B0 2B 电压 → 12.60V（回归）。
- 81 0x0D 空 D → 仅 alarm/state；81 带 D → 原文 + warning。
- 84 不变。

**验收**：M-4 的“0.01V 假电压”只在 4B 畸形短帧/非 2B D 时出现且带 warning；合法 B0/C0 电压不回退。

---

### WP-5 45H 状态数据位宽（规模 S）

**覆盖**：v2.6 L-6、补充 L-15。

**修复设计**

- `_parse_status` docstring 改为：“表58 定义 BIT0~BIT11（BIT12~31 保留）；表60 规定遥测站状态数据为 4 字节 HEX。本实现兼容 2B/4B，取低 12 位；4B 且保留位非零时给出可见提示。”
- `docs/project.md §2.3` 与 Roadmap 同步为“数据宽度 4B、有效位 12”；删除“表58 仅定义 12 位 ⇒ 32 位不存在”的混淆表述，改成“位定义 12 个，数据宽度 4B”。
- 4B 且 `sv >> 12 != 0`：追加一个 `ElementValue(code="45-reserved", name="保留位(BIT12~31)", value=f"0x{sv>>12:X}", ...)`，作为可见提示（不改 `warnings` 通道，避免大改 `_parse_status` 签名）；若审计要求 warnings，则改为 `_parse_status` 返回 `(elements, warning)` 并由 `_make_element` 传递。
- 2B 状态数据继续支持（历史样本兼容），文档注明“规约表60 为 4B，2B 为兼容旧设备”。

**测试**

- 4B 状态 + BIT12 置位 → 出现“保留位”提示，BIT0~11 正常。
- 4B 全 0 → 12 位正常，无提示。
- 2B 状态仍正常。
- 全 FF/AA 填充仍降级 `-`（不回归 v2.4）。

---

### WP-6 编码器入口校验与异常契约（规模 M）

**覆盖**：v2.5 L-9、L-10；v2.6 L-2；补充 L-13。

**修复设计**

1. 共享校验助手（`sl651/encoder.py` 或 `sl651/validation.py`）：
   - `_check_guide(g)`：`0 <= int(g) <= 0xFF`，否则 `EncodeError`；
   - `_check_number(v, name)`：拒绝 `bool`/`str`/`None`/`NaN`/`inf`，否则 `EncodeError`；
   - `_check_int(v, lo, hi, name)`：类型/范围；
   - `_encode_bcd`：先 `_check_number`，再 `round`；捕获 `ValueError/OverflowError/TypeError` 统一转 `EncodeError`。
2. `_check_datetime`：`isinstance(datetime)` + `2000 <= year <= 2099`；覆盖 `build_frame(tx_time)`、`build_timing/alarm/hourly`、`build_clock_sync_frame` 等所有入口。
3. `build_frame`：`direction in (0, 1)`；`end_marker` 0~255；`ascii_mode` 严格 bool（可选）。
4. SL651 各 body：`build_timing_body`/`build_alarm_body`/`build_set_param_body`/`build_query_body`/`build_ascii_body` 的 guide 统一 `_check_guide`；`data_len`/`decimals` 由 `_make_def_byte` 校验；数值由 `_encode_bcd` 校验。
5. SL427：
   - `build_heartbeat(hb_type)`：只允许 `HEART_MAP` 的键（0xF0/0xF1/0xF2），否则 `EncodeError`；
   - `build_set_work_mode(mode)`：只允许 0/1/2/3，否则 `EncodeError`；
   - `build_self_report_c0/81/82`、`build_query_response`：`alarm/state` 必须 `int` 且在 0~65535；
   - `build_self_report_84`：`0 <= voltage <= 99.99` 且有限，报错文案改为“0~99.99V”；
   - `build_set_clock`：年份 2000~2099；
   - `build_param_set_frame`：`encode_pw` 改抛 `EncodeError`（当前 `encode_pw` 抛 `ValueError`）；
   - 所有 `int(round(x))` 入口（`build_set_recharge`、`build_set_recharge_alarm`、`build_set_level_limits`、`build_set_pressure_limits`、`build_set_water_quality`、`build_set_water_amount`、`build_set_flow_limits` 等）先走 `_check_number`，避免 NaN/inf/str 泄漏裸异常。
6. `make_ctrl`：可选校验 `dir_ in (0,1)`、`func_code 0..15`、`fcb 0..3`、`div 0..1`；若担心影响调用方，先在 `build_*` 入口校验，`make_ctrl` 保持宽容（见 Q7）。

**测试**（新增 `tests/test_protocol_contracts.py`）

- 参数化非法输入：guide `0x1FF/-1/"05"`；value `NaN/inf/"1.0"/None`；`direction=2`；`obs_time=1999/2100`；`mode=-1/4/255`；`heartbeat=-1`；`alarm=-1/70000`；`voltage=-1/100/NaN`。
- 每个用例断言 `EncodeError`（不是 `ValueError/OverflowError/TypeError`），并 `except sl651.errors.EncodeError` 能跨包捕获。
- 合法边界：year 2000/2099、mode 0/3、heartbeat 0xF0~0xF2、voltage 0/99.99、guide 0/0xFF。
- `build_self_report_84(99.99)` 正常、`100` 报错。

**验收**：C5 成立；公开编码方法不再泄漏裸异常；旧测试中的 `EncodeError` 导入路径仍工作。

---

### WP-7 小时报数组、地址方式、A 补齐、F5 定义符（规模 M）

**覆盖**：v2.5 L-3；v2.6 L-1、L-3、L-5；补充 L-17。

**修复设计**

1. **小时报（`build_hourly_body`）**
   - `water_levels[i] is None` → `FFFF`（合法缺测）；`< 0` → `EncodeError`（“负水位无法用 F5 无符号数组表达，请改用可表达负数的要素/相对水位基值”）；`> 655.34` → `EncodeError`（655.35 是非法标记）。
   - `rain_amounts[i] is None` → `FF`；`< 0` 或 `> 25.4` → `EncodeError`（25.5 是非法标记）。
   - 先做范围判断再 `round`，避免 25.45 被四舍五入成 25.4 的静默损失。
   - docstring 修正：F4 “各 1B”而不是“各 2B”；F5 定义符改 `_make_def_byte(24, 0)`（表C.1 HEX 数组不赋予小数位语义，北京语料 7/7 为 0xC0；与 F4 的 0x60 口径统一）。
   - `inst_level`/`voltage` 走 `_encode_bcd` 校验。
2. **地址方式往返（`encode_address`）**
   - 方式1：`admin_code` 必须 6 位且首字节非 00H。建议 `110000 <= admin_code <= 829999`（GB/T 2260 省级码 11~82）；至少 `>= 100000`。默认值由 0 改为 `110000`（`stn_id=1`），文档标注默认值变更。
   - 方式2：保持 8 位 HEX 校验。
   - 测试：`admin_code=0/9999/100000/109999` → `EncodeError`；`110000/110105/710000/820000` 往返；`encode_address()` 默认值被自家 `_format_addr` 判为方式1。
3. **A 补齐 BCD（按 Q4 裁决）**
   - `bcd.py`：`bcd_to_int`/`bcd_bytes_to_int` 增加 `allow_a_pad=False` 关键字；`int_to_bcd_bytes_a(value, length)`（最高半字节 A，其余 BCD）。
   - `decoder._safe_bcd_val(..., allow_a_pad=False)`；`_parse_elements` **仅在 40H~43H 配置帧路径**检测首半字节 A 且其余合法 → 按 A 补齐解码 + warning；定时报/普通要素路径保持 `-`（非首 A 仍 `-`）。
   - `encoder.build_set_param_body(params, a_pad_guides=frozenset())`：显式指定按 A 补齐的 guide；新增 `_encode_bcd_a`；`build_set_param_frame` 透传。
   - 测试：解码 `A13812345678` → `13812345678` + warning；编码 `a_pad_guides={0x05}` → `A13812345678`；非首 A 仍 `-`；普通 BCD 不受影响。
4. **F5 定义符**：见上，测试断言 F4=0x60、F5=0xC0，且解码不受定义符小数位影响（仍 0.01m）。

**验收**：v2.5 L-3、v2.6 L-1/L-3/L-5、L-17 的复现全部闭环；真实语料（福建/北京）要素级基线不变。

---

### WP-8 CLI 脱敏（规模 S）

**覆盖**：v2.5 L-7；v2.6 L-4；补充 L-12。

**修复设计**

1. 在 `tools/decode_cli.py` 增加统一脱敏助手：
   - `mask_center(s)` → `**`（1 字节字段不再 `[:2]+"**"`）；
   - `mask_station(s)` → 前 2 个 HEX 字符 + `********`；
   - `mask_raw(hex_str)` → 保留前 2 字节 + `…` + 长度，例如 `7E7E…（46 字节，已脱敏）`；
   - `mask_error(msg)` → 只保留“协议/长度/错误类型”，不回显完整输入。
2. `format_sl651`/`format_sl427` 的“原始报文”行使用 `mask_raw`；`_sanitize_dict` 同步；JSON `errors[].message` 改为 `mask_raw` 或“第 N 条（长度 X）”。
3. 新增 `--show-raw`（默认关闭）：显式打印完整 hex；文档标注“仅本地调试，日志场景勿用”。
4. 更新 `test_cli_json_masking`：断言 `center_addr == "**"`、`station_addr` 前 2 位 + 星号、`password == "****"`、输出中不含完整输入 hex；新增 text 输出与 errors 路径断言；`--show-raw` 恢复完整。
5. Web `web/app.py` 的中心/站址展示是否同步脱敏：建议同样默认遮（本地调试可通过前端“显示完整”开关，若工作量小则本轮一并做；否则列入 P4）。本方案将 Web 列为可选，不阻塞 CLI。

**验收**：三条审计复现（text 原文、JSON errors、center 空操作）全部不再泄漏；`--show-raw` 可用；现有 JSON 契约测试更新后通过。

---

### WP-9 TcpSender 持锁重连（规模 S）

**覆盖**：v2.6 L-7。

**修复设计**

- `TcpSender.send()` 不在持锁状态 `sleep(1)`：先判断连接状态；需要重连等待时释放锁、`time.sleep(self.reconnect_delay)`，再重新加锁尝试连接/发送；连接失败直接返回 False。
- 新增 `reconnect_delay: float = 1.0` 构造参数（默认保持 1s）；文档说明“连接建立仍受 `timeout` 限制，但等待不再串行化所有站点”。
- 可选进一步：用 `_conn_lock` 保证同一时刻只有一个线程建连，其他线程快速失败/等待短超时；本轮先做“锁外等待”，避免大改。
- 测试：两个线程共享一个 `reconnect=True`、无监听端口的 `TcpSender`，monkeypatch `time.sleep` 记录调用；断言 sleep 不在 `_lock` 持有期间（或总耗时 < N×delay）。至少加一个“`send` 失败返回 False 且不抛异常”的回归。

**验收**：链路断开时多站点发送不再被 1s×N 串行阻塞；线程安全测试通过。

---

### WP-10 YAML 配置校验（规模 S）

**覆盖**：v2.5 L-5。

**修复设计**

- `simulate_cli.py` 新增：
  - `_parse_function_code(v)`：接受 `int`（0~255）或 `"0x.."` 字符串；拒绝 bool/其他类型/越界；限制为 **`{0x30, 0x32, 0x33}`**（0x31 均匀报、0x34 小时报 F4/F5 数组、0x35 人工置数 F2、0x36 图片的正文结构均不同；`StationRunner` 恒用 `build_timing_frame`，放行会发出“CRC 合法但正文错误”的帧）。
  - `_validate_alert_threshold(v)`：有限、`>= 0`。
  - `_load_config` 中 `engine.add_station(...)` 包 `try/except EncodeError`，输出 `stations[i] 配置错误: ...` 并 `return 1`，不裸 traceback。
  - CLI 主路径 `engine.add_station` 同样捕获 `EncodeError`，`parser.error` 友好退出。
- 文档：YAML 示例注明 `function_code` 用十六进制字符串或整数，推荐 `"0x33"`。

**测试**：`function_code: 33`（十进制歧义）→ 拒绝并提示；`"0x33"` → 接受；`"abc"`/列表 → 拒绝；`alert_threshold: "x"`/`-1` → 拒绝；`center: 300`/`password: 70000` → 装载期可读错误（非 traceback）。

**验收**：审计 L-5 的两个复现（0x21 静默发出、线程内 TypeError）均变为装载期明确报错。

---

### WP-11 雨量站 0x1F/0x20 语义（规模 S）

**覆盖**：补充 L-16。

**修复设计**

- 按规约 3.1.7/3.1.8：
  - `0x1F` 日降水量 = 上一日 24h 总量；
  - `0x20` 当前降水量 = 最近日起始时间至当前累计。
- `RainGenerator` 增加 `previous_day_accum`；日重置时 `previous_day_accum = daily_accum; daily_accum = 0`。
- `RainStation.generate_elements`：`0x1F` 用 `previous_day_accum`，`0x20` 用 `daily_accum`；`0x26` 继续用不归零 `total_accum`。
- 初始 `previous_day_accum=0`（首日无上一日数据）。
- 测试：模拟跨 1440 分钟 + 降雨，断言 0x1F 与 0x20 不再恒等；日重置后 0x1F=前一日总量、0x20 从 0 开始。

**验收**：审计 L-16 的“恒相等”消失；其余要素（0x1A/0x26/0x38）不变。

---

### WP-12 MqttxSender 安全与进程模型（规模 S，按 Q6 裁决）

**覆盖**：v2.5 L-8。

**修复设计（推荐 v1.4.0 最小闭环）**

- README/simulator README 增加安全说明：MQTT 密码经 `mqttx pub -P` 传递，可能出现在进程列表；建议使用专用低权限账号/受限 broker。
- 密码非空时 `logger.warning` 一次（“MQTT 密码经命令行传递，存在进程列表暴露面”）。
- P4 Roadmap 记录“可选 paho-mqtt 长连接 Sender”，不在本轮引入依赖。
- 若 Q6 裁决要求本轮解决：新增 `PahoMqttSender`（可选 import，缺依赖时回退 mqttx），并补集成测试；工作量升为 M。

**验收**：文档有明确安全边界；无功能回归；若做 paho，则 mqttx 回退路径仍可用。

---

### WP-13 文档、版本、测试计数、收尾（规模 M）

**覆盖**：补充 L-14、潜伏观察、全部文档同步。

**修复设计**

- 删除 `sl651/decoder.py` 未使用的 `safe_bcd_to_int` 导入（若 WP-7 需要则改为显式使用）。
- `__version__ = "1.4.0"`；README 版本历史新增 v1.4.0 条目（M/L 修复摘要 + 新 API + 行为变更）。
- `docs/project.md`：
  - §2.3 45H 位宽；
  - §2.5 `feed()` 上限/TTL/错误通道/旧方言；
  - §2.6 编码器校验契约、`divs`、`a_pad_guides`；
  - §3.2 SL427 DIV 重组/单帧降级；
  - §3.3 0x0D 上下文矩阵；
  - §7 测试清单/计数；
  - §8 Roadmap 关闭已完成项，新增“附录D 参数名完整映射 / paho-mqtt / Web 脱敏”。
- `docs/handoff_main.md`：版本、轮次（v2.5/v2.6/补充）、TODO 闭环、设计决策（分帧 AUX 假设、跨报文残余风险、异常类统一）。
- `docs/handoff_test.md`：测试计数标注为实测值（不写死），新增套件说明。
- 各模块 README：`sl651/README.md`（`feed`/错误通道）、`sl427/README.md`（DIV/`feed`/`divs`）、`tools/README.md`（`--show-raw`）、`simulator/README.md`（MQTT 密码边界）。
- 审计归档：由审计会话把 L-12~L-17 补为 `audit/audit_report_v2.6_addendum.md`；**建议与 P0 开工同期完成**（否则 6 项出处只有对话记录，审计轨迹不闭合）。`audit/plan_review_v1.4.0.md` 入库；主会话只在新 plan/README 中引用，不改审计结论。
- `run_all.py` 增加 2 个新套件；CI 矩阵不变；测试计数以最终实测为准。
- 提交前跑：`python3 -B tests/run_all.py`、福建 23 条、北京 25 条、`python3 -m compileall`；`git status` 只含预期文件。

---

## 5. 测试计划

### 5.1 新增套件

**`tests/test_sl427_multiframe.py`**（约 10 组）

| 编号 | 用例 | 断言 |
|---|---|---|
| MF-1 | B0 两帧 DIVS=2/1 | 重组 == 单帧（要素名/值/raw） |
| MF-2 | B1 两帧 | 重组结果与单帧一致 |
| MF-3 | 83/61 图片两帧 | **阻塞项**：L×1K 语义未证前不作为通过用例，只做安全降级 |
| MF-4 | 缺帧/缺号 | 无要素、errors 有记录、不产生垃圾告警 |
| MF-5 | 乱序 2/3/1 同批 | 可重组 |
| MF-6 | 跨批次 2 后 1 | 可重组（单帧末片需带 warning） |
| MF-7 | 坏 CRC 分片 | 整组不输出/不声称 `crc_ok=True` |
| MF-8a | `decode()` DIV=1/divs>1 | 空要素 + warning |
| MF-8b | `feed()` 单 DIVS=1（`allow_single_div=True`） | 单帧解析 + warning；默认不解析 |
| MF-9 | encoder `divs=2/1` | `feed()` 还原 |
| MF-10 | 组数/字节/TTL 上限 | 有界、最旧淘汰、无异常 |
| MF-11 | C0/81/82/FF 的 DIV 帧 | 安全降级 + warning，不拼 AUX |

**`tests/test_protocol_contracts.py`**（约 12 组）

| 编号 | 用例 | 断言 |
|---|---|---|
| PC-1 | 4 个异常类别名同一性 | `is` 全等 |
| PC-2 | guide/NaN/inf/str/None | 全部 `EncodeError` |
| PC-3 | direction/year/mode/heartbeat/alarm | 全部 `EncodeError` |
| PC-4 | 小时报边界/None/负值/25.4/655.34 | 合法通过、非法 `EncodeError` |
| PC-5 | 地址方式 0/9999/100000/110000/820000 | 往返或 `EncodeError` |
| PC-6 | A 补齐解码（仅 40H~43H）/编码 | 值正确 + warning；普通要素路径仍 `-` |
| PC-7 | 填充/综合参数/信道 | `-` 或“无”，无静默省略 |
| PC-8 | 0x0D 矩阵（B0/C0/81/82/84 + 4B 短帧 + 15B D=4B） | B0/C0/84 电压保持；81 无电压；异常 D 长度原文 + warning |
| PC-9 | 45H 4B 保留位 | 提示出现、低 12 位正常 |

### 5.2 扩展套件

- `test_sl651_multipacket.py`：加“误码包/跨报文/`_pending` 上限/旧方言/前导垃圾同批”5 组。
- `test_fuzz_decoders.py`：加 SL427 DIV 变异帧、SL651 SYN 翻位正向断言（不得 `crc_ok=True`）。
- `test_sl651.py`：更新 `test_cli_json_masking`；加小时报边界、F5 定义符、45H 保留位、A 补齐（或放 PC）。
- `test_simulator_integration.py`：加 TcpSender 锁外等待、YAML 非法值、雨量 0x1F/0x20。
- `run_all.py`：新增 2 套件，8 → 10。

### 5.3 测试编写规约（评审新增）

- **分帧/多包用例必须按规约表 3/表 22/B 系列手工拼帧**，不得仅用项目自身构造器；用项目构造习惯构造的测试是自洽循环，正是 v2.5 M-1、v2.6 M-1 连续漏报的根因之一。
- 每个修复至少保留一个“审计复现”用例（输入、期望、实际三列），并在测试注释中标注发现编号。
- 任何“降级”用例必须同时断言：不抛未受控异常、不产出错误值、`warnings`/errors 可见。

### 5.4 回归门禁（每个 WP 完成后都跑）

1. `python3 -B tests/run_all.py` → 10/10；
2. 福建 23 条 / 北京 25 条 → CRC + 要素级基线不变；
3. 所有审计复现脚本（v2.5 M-1/M-2/M-3/M-4、v2.6 M-1、L-12~L-17）→ 预期结果；
4. 无裸 `ValueError/TypeError/OverflowError` 从公开编解码入口泄漏（可用参数化测试 + `except ProtocolError`）；
5. `compileall` + `git diff --check`；
6. 两个审计会话分别复核其报告中的缺陷闭环。

---

## 6. 实施顺序、提交与回滚

### 6.1 顺序

```
P0  WP-0（异常/warnings）
P1  WP-1（SL651 SYN/feed） + WP-2（SL427 DIV）      ← 数据完整性，先做
P2  WP-3（填充/综合参数） + WP-4（0x0D） + WP-5（45H）
P3  WP-6（编码器校验） + WP-7（小时报/地址/A补齐/F5）
P4  WP-8（CLI 脱敏）
P5  WP-9（TcpSender） + WP-10（YAML） + WP-11（雨量） + WP-12（Mqttx）
P6  WP-13（文档/版本/计数/CI） → 全量回归 → 审计复核 → tag v1.4.0
```

P1 完成即设**审计检查点 1**（只验 M-1/M-3/DIV，不继续往下做），避免在错误底座上堆改动。**WP-2 开工前必须先完成 83/61 的 `L×1K` 语义核验；核验不了则 83/61 只做安全降级，MF-3 不作为通过项。** P3 完成设**检查点 2**（编码器契约 + 审计复现）。P6 前设**检查点 3**（文档/计数/真实语料）。

### 6.2 提交

- 分支：`fix/v1.4.0`；一个 WP 一个 commit（或 WP 内小步 commit），commit message 带发现编号（如 `fix(sl651): verify per-packet CRC in SYN reassembly (v2.5 M-1)`）。
- 每个 commit 自带测试；不把“修代码”和“改文档计数”混在一个 commit 里（WP-13 除外）。
- 不修改 `audit/` 既有报告；新增 addendum 由审计会话提交。

### 6.3 回滚

- WP-1/WP-2 的状态机改动集中在 `SL651Decoder`/`SL427Decoder`，可整体 revert；
- `SL427Decoder.feed()` 为新增方法，`decode()` 的 DIV 安全降级可单独保留；
- CLI `--show-raw` 默认关闭；如需回滚脱敏，仅改 CLI 层，不影响库；
- 地址默认值/严格校验如引发兼容问题，回滚为“默认合法值 + `strict` 参数”，但需审计重新裁决 Q7。

---

## 7. 非目标（本轮不做）

- 附录D 全部配置参数名称/布局的完整映射（本轮只做 A 补齐 BCD 最小闭环）；
- SL427 下行参数/查询帧的数据域回显（handoff 既有 P2 项）；
- paho-mqtt 长连接（除非 Q6 裁决要求）；
- Web 前端重做/请求体上限（v2.5 备忘，非缺陷）；
- 45H 保留位 32 位的“全量解析”（规约只定义 12 位，本轮只做可见提示）；
- 修改历史审计报告的结论/分级。

---

## 8. 追踪矩阵

| 发现 | 级别 | WP | 关键测试 | 文档 |
|---|---|---|---|---|
| v2.5 M-1 | M | WP-1 | 误码包不得 `crc_ok=True`；跨报文重置 | project §2.5、handoff |
| v2.5 M-2 | M | WP-3 | 综合参数填充块不吃下一块 | project §3.2 |
| v2.5 M-3 | M | WP-1 | 3000 帧有界；坏帧 errors | project §2.5 |
| v2.5 M-4 | L（评审降级） | WP-4 | B0/C0 电压保持；4B 短帧/非 2B D 降级 | project §3.3 |
| v2.5 L-1 | L | WP-3 | 标量填充 `-` | README |
| v2.5 L-2 | L | WP-1 | 旧方言 `feed()` | sl651 README |
| v2.5 L-3 | L | WP-6/WP-7 | F4/F5 边界、84 文案 | README |
| v2.5 L-4 | L | WP-0 | 异常同一性 | project §2.7 |
| v2.5 L-5 | L | WP-10 | YAML 非法值装载期报错 | tools README |
| v2.5 L-6 | L | WP-0 | 并发 warnings 不串 | handoff |
| v2.5 L-7 | L | WP-8 | text 原文脱敏 | tools README |
| v2.5 L-8 | L | WP-12 | 安全说明/warning | simulator README |
| v2.5 L-9 | L | WP-6 | 年份越界 `EncodeError` | project §2.6 |
| v2.5 L-10 | L | WP-6 | direction 越界 | project §2.6 |
| v2.5 L-11 | L | WP-1 | 垃圾+好帧同批 | sl651 README |
| v2.6 M-1 | M | WP-2 | 分帧重组/单帧降级 | sl427 README、project §3.2 |
| v2.6 L-1 | L | WP-7 | 地址往返 | project §3.4 |
| v2.6 L-2 | L | WP-6 | guide/NaN/inf/mode | project §2.6 |
| v2.6 L-3 | L | WP-7 | 负水位/负雨量 | README |
| v2.6 L-4 | L | WP-8 | errors 路径脱敏 | tools README |
| v2.6 L-5 | L | WP-7 | A 补齐往返 | project §2.3 |
| v2.6 L-6 | L | WP-5 | 45H 4B 提示 | project §2.3 |
| v2.6 L-7 | L | WP-9 | 锁外 sleep | handoff |
| v2.6 L-8 | L | WP-3 | 信道 0xFF | project §3.2 |
| 补充 L-12 | L | WP-8 | center 全遮 | tools README |
| 补充 L-13 | L | WP-6 | mode 0~3 | project §3.6 |
| 补充 L-14 | L | WP-0/WP-13 | 死导入移除 | — |
| 补充 L-15 | L | WP-5 | 45H docstring | project §2.3 |
| 补充 L-16 | L | WP-11 | 0x1F/0x20 不恒等 | simulator README |
| 补充 L-17 | L | WP-7 | F5 0xC0 | project §2.3 |
| 潜伏 `_safe_hex_val` | 观察 | WP-3/WP-13 | 注释 + 未来用例 | project §2.7 |

---

## 9. 请审计复核的 5 个最终判断

1. **Q1 的 0x0D 矩阵**：B0/C0 的 0x0D 均为 2B 电压（§7.3.22 n) + 表24 D12），81 无中间参数；报告 4B 短帧与审计 B 15B D=4B 都是非标准帧，M-4 降 L。
2. **Q2 的保守分帧**：只重组 B0/B1/84；83/61 因 `L×1K` 未证而阻塞；C0/81/82/FF 安全降级。请确认该保守边界。
3. **Q3 的跨报文残余**：已采纳“有界 + 可观测 + 同 seq 不同内容重置”，不采纳同批次严格模式；残余风险文档化。
4. **Q4 的 A 补齐范围**：仅 40H~43H 配置帧启用，普通要素路径保持拒绝；不作附录D 全量映射。
5. **Q5/Q7 的默认行为变更**：CLI 默认脱敏、`encode_address` 默认值/严格范围、mode/heartbeat 严格校验，是否接受为 v1.4.0 的 breaking-ish 变更。

---

> 本文原为方案稿；v1.4.0 已按本文落地（`run_all.py` 10/10），保留作为评审与实施记录。所有对比基线以 `5b02471` 为准。
