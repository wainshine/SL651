# SL651-Toolkit 代码审计报告 v2.8

> 审计日期：2026-11-05
> 审计角色：主会话独立审计（只审不修）
> 基线文档：`docs/project.md` v1.4.2、`README.md` v1.4.2
> 基准代码：v1.4.2（git `fcdeb9f`；主体修复 `13bef9f` + 自审计 `a7e67bc` + fixture 补充 `fcdeb9f`，工作区干净）
> 审计方式：五层审计模型（规约条文比对 / 全量常量基线 diff / 构造性回放 / 随机变异 8000 帧 / 历史缺陷复核）
> 审计范围：`sl651/`、`sl427/`、`simulator/`、`tools/`、`web/`、`tests/`（含新 fixture）、全部文档
> 规约依据：SL651-2014 txt + 报批稿 PDF（第 44~48/76 页）、SL427-2021 PDF（第 11/14/24/31 页）
> 与 v2.7 的关系：v2.7 的 2M+7L 已在 v1.4.2 全部闭环（本报告 §五验收确认）；本轮是针对 **v1.4.2 新代码与新提交的独立复审**

---

## 一、审计结论总览

| 严重度 | 数量 | 状态 | 说明 |
|--------|------|------|------|
| Critical (C) | 0 | — | `run_all.py` 11/11；SL651 三个新路径 8000 帧变异零未受控异常 |
| Medium (M) | 2 | 🆕 本轮新增，均由 v1.4.2 新代码引入 | M-1 ASCII pH 标识符「表键-查找」断链（`fcdeb9f` 大小写修正引入的回归）；M-2 SL427 分帧重组直接解析绕过异常保护，`ValueError` 从 `feed()` 裸泄漏 |
| Low (L) | 2 + 1 Info | 🆕 本轮新增 | L-1 B1 多记录静默截断无 warning；L-2 B1 起止时间无日历合法性校验；L-3 经复核降为 Info 文档说明（「PDF 快照」表述在测试 docstring 而非 fixture） |
| v2.7 闭环复核 | 2M+7L | ✅ 全部确认修复 | 见 §五 |

**核心结论**：v1.4.2 的主体修复质量高——16 位长度四处同源、重组直接解析、表 C.1/G.1 拆分、fixture 逐行断言都正确落地；**两个新 Medium 都发生在「新路径与既有约定的接缝处」**：M-1 是表键规范化（`pH`）与查找规范化（`upper()`）用了两套逻辑，M-2 是新解析入口（`_decode_div_reassembled`）没有继承旧入口（`decode()`）的异常保护。这两条再次验证了项目已确立的横向规律——**同源判定必须单点实现、新入口必须继承旧入口的全部契约**。

---

## 二、中等缺陷（Medium）

### M-1 ASCII pH 标识符「表键-查找」断链：规约修正让 pH 要素在解码路径失效

**位置**：`sl651/constants.py:376`（`"pH": ("pH", "")`，`fcdeb9f` 由 `PH` 改来）、`sl651/decoder.py` `_parse_ascii_elements`（查找为 `C.SL651_ASCII_ELEMENTS.get(code.upper())`）。

**问题**：表 C.1 中 46H 的 ASCII 码按规约确为 `pH`（小写 p，规约行 4196；PDF 第 46 页），`fcdeb9f` 把表键从 `PH` 修正为 `pH` 是对的；但解码器查找路径是 `code.upper()`——报文里的 `pH` token 被大写成 `PH` 再查表，而表中已无 `PH` 键。**结果：pH（水质核心要素）在 ASCII 解码路径的名称/单位丢失，显示「未知(pH)」**，回归前（v1.4.1 及以前，键为 `PH`）是正常的。

**实测**：`build_ascii_frame([("pH","7.2")])` → 解码得 `[PH] 未知(pH) = 7.2 ''`（对照 Z 要素正常）。

**为什么自家测试没抓住**：同一提交新增的 `test_fixture_c1_full` 直接断言表键（`"pH" in C.SL651_ASCII_ELEMENTS and "PH" not in`），**没有经过解码器的查找路径**——行级 fixture 测试与运行时查找脱节，恰好测不出这条断链。

**修复建议**（经对抗复核修订——原「`get(code) or get(code.upper())` 两分支」方案经验证不完整：对历史/厂商可能使用的 `PH`/`ph` 令牌，`get(code)` 与 `get(code.upper())` 均为 None，仍然漏）：
1. **单点大小写无关查找**：建立一次性 `{k.casefold(): (k, v)}` 索引或 `_lookup_ascii(code)` 帮助函数，查 `code.casefold()`；表键仍按规约保留 `pH` 原样。多值收集处的 `nxt.upper()` 与主查找**必须是同一处修复**（同一函数），否则 `pH` 作为后续 token 时行为不一致；
2. 不变量测试必须**穿透查找入口**：对表中每个 key，`_lookup_ascii(key)`（或 `_parse_ascii_elements` 实际路径）必须命中——只断言「表键存在」测不出本次断链（本轮 fixture 测试即为例证）；
3. `pH` 是全表唯一混合大小写键，修完后由该不变量测试长效防护。

### M-2 SL427 分帧重组直接解析绕过异常保护：非法 BCD 的 ValueError 从 feed() 裸泄漏

**位置**：`sl427/decoder.py:989`（`_decode_div_reassembled` 直接调用 `self._parse_data_field(...)`，未经过 `decode()` 的 `except (ValueError, IndexError) → DecodeError` 包装）；泄漏点示例 `sl427/decoder.py:1364`（B1 分派）→ `_parse_ctrl_func_data` → `bcd_bytes_to_int_le` → `bcd.py:13 raise ValueError("无效 BCD 字节…")`。

**问题**：v1.4.2 把 DIV 重组从「`decode(synthetic)`（受保护）」改为「直接调 `_parse_data_field`（不受保护）」，畸形 BCD 数据在分帧重组路径上裸抛 `ValueError`。规约/工具契约（project.md §2.5、v1.3.2 L-3 确立的「畸形拒绝契约」）要求解码器只抛受控 `DecodeError`。**定级说明（复核修订）**：本缺陷按当前影响定级 Medium——仅 DIV 重组路径、仅畸形输入、表现为抛异常而非静默错值；「v1.2.5 H 级历史缺陷复活」仅为缺陷谱系类比，不作为本轮定级依据。

**实测**：随机变异 8000 帧（二进制 SYN 3000 / 流式切碎 SYN 1500 / ASCII SYN 1500 / SL427 DIV 2000），**395 个未受控异常全部来自 `div427`——该比例（≈5%）仅在本次变异配置（seed=20261105、特定长度/内容分布）下成立，不代表现场误码率**。典型：`AFN=0xB1 func=0x08 payload=dc17f0…` → `ValueError: 无效 BCD 字节: 0x7D`，完整栈：`feed → _handle_div_frame → _decode_div_reassembled → _parse_data_field → _parse_ctrl_func_data → bcd_bytes_to_int_le → bcd_to_int`。SL651 三个新路径零泄漏（其解析内部本就非抛出式）。

**为什么自家测试没抓住**：`tests/test_fuzz_decoders.py` **没有任何 DIV 分支**（grep 无 `div`）——v1.4.1 时代的 DIV 变异走的是 `decode(synthetic)` 受保护路径，重构后无人在变异套件里补 DIV+非法 BCD 组合。

**修复建议**（经对抗复核修订，替代原「一行 try/except」表述）：
1. **单点受保护入口**：提取 `_parse_data_field_protected()`（`except (ValueError, IndexError) → 降级原始摘要 + warning「重组数据解析失败: …」`），`decode()` 与 `_decode_div_reassembled` 共用——B0/84/B1 **全部**直接解析路径由同一入口覆盖，不得只包个别调用点；不得吞 `DecodeError`（其必须继续向调用方传播）；解析失败时降级为原始摘要 + warning，不得把整条重组消息无提示丢弃；
2. `tests/test_fuzz_decoders.py` 补 SL427 DIV 分支（含非法 BCD payload、坏 CRC 分片、乱序、大 payload）——根因修复；
3. 防御性对称：SL651 `_decode_reassembled` 直接调 `_decode_binary/_decode_new_ascii`，当前实测安全（内部非抛出式），但建议同样走受保护入口，避免下一个重构再踩一次。

---

## 三、轻微问题（Low）

| # | 位置 | 问题 | 验证 |
|---|------|------|------|
| L-1 | `sl427/decoder.py` B1 分支（`:1360-1380` 附近） | **B1 多记录静默截断**：表48 头后的存储数据按 `func_code` 单条解析，剩余记录字节无 warning 丢弃。实测 B1/func=0x01（雨量，单条 3B BCD）12 条记录 → 仅输出 1 条「雨量: 100.0」，33B 数据无痕消失。自审计残余 #2 已声明「数组展开待实现」，但「静默」违背本项目「降级必须留痕」原则。**修复前置（复核修订）**：不能直接「rest 非空就 warning」——`_parse_ctrl_func_data` 只返回元素不返回消费字节数，合法多值会误报；需先把其改为返回 `(elements, consumed)`，或 B1 分支按 `func_code` 的记录长度计算 `record_count` 后再决定 warning 措辞 | 实测 |
| L-2 | `sl427/decoder.py` B1 起止时间 | **起止时间无日历合法性校验**：合法 BCD 但越界的值照常格式化，实测显示「2002-01-24 **30**:00」「20**15**-**23**-02」。与 v1.2.6 B1 确立的「无效 BCD 半字节占位显示」政策不对齐（半字节非法有占位，字节值越界无提示）。建议越界（月>12/日>31/时>23）时占位或 warning | 实测 |
| L-3→Info | `tests/test_constants_spec.py:96`（docstring） | **「PDF 表 C.1 快照」表述与实际不符，定位为文档说明**（复核修订：原报告误将此句归于 fixture 文件——经核验 `sl651_table_c1.tsv` 内无任何「快照」字样，仅有表头，该句在测试 docstring）。实质不变：fixture 的 (guide→ASCII) 映射 **131/131 精确一致**、单位全部语义正确，但 49 处名称列为工具显示名（38H「电池电压」vs 规约「电源电压」、3BH「坝上水位」vs「库(闸、站)上水位」等），docstring 的「PDF 快照」表述会误导维护者按字面理解。建议 docstring 改为「工具显示口径基线（名称/单位为显示名，规约原文见 PDF 第 44~48 页）」；38H 可顺手对齐为「电源电压」。降为 Info，不计缺陷 | 全量 diff |

---

## 四、规约符合性复核与全量基线比对（Layer 1）

1. **表 C.1 全量独立 diff（本轮新增手法）**：用独立解析器从规约 txt 提取 131 行 (guide, ASCII码)，与 `tests/fixtures/sl651_table_c1.tsv` 逐行比对：**映射 131/131 一致、无多余/缺失行、单位全部语义正确、49 处名称差异全部为转述**（L-3）。fixture 作为测试基线可信。
2. **`pH` 大小写**：规约 ASCII 码确为 `pH`（表C.1 行 46），`fcdeb9f` 修表方向正确，错在查找路径（M-1）。
3. **表22/表23 SYN 长度语义**：实现按 bit7 判别（=1 下行 12 位 / =0 上行 16 位）、legacy 0101 保持 12 位——四处（`_extract_frame`/`_handle_syn`/`_find_valid_start`/`_decode_binary`）同源，与本轮 PDF 裁决一致 ✅。
4. **B1 表48 头**（9B = 参数种类 D7~D4+编号 D3~D0 + 起止时分日月×2）与 SL427 PDF 第 31 页一致 ✅。
5. **表G.1 隔离**：`_parse_ascii_elements` 不引用 G 表；G 表 12 核心码（SD=日平均含沙量等）与资料性附录定位一致 ✅。
6. 76H~EFH 保留区未收录（80H 厂商自定义除外）、FDH 走 RAW 摘要不数值化 ✅。

---

## 五、v2.7 闭环验收（Layer 4）

| v2.7 项 | 验证方式 | 结果 |
|---------|----------|------|
| M-1 要素表 | 132/130/G 独立 + fixture 全量 diff + 58H 解码 | ✅（58H=水压1/kPa，实现以 PDF 为准） |
| M-2a 重组 >4095 | 5050B 两包 `feed()` | ✅ 重组成功 |
| M-2b SL427 >255 | 300B 两片 `feed()` | ✅ 直接解析 |
| M-2c 单包 16 位 | 5003B 单包 `feed()`/`decode()` | ✅ |
| L-1 分类码 | 编码 `K`、解码 `K`=水库、`4B` 兼容+warning | ✅ |
| L-2 ASCII 包号 | `00A001` 按 HEX 入缓存 | ✅ |
| L-3 直解分包 | `total>1` 空要素+warning、`total==1` 正常 | ✅ |
| L-4/L-5 | N(6,1) 文档；YAML center 1~254 校验 | ✅ |
| L-6/L-7 | B1 表48 头；84 超长 warning | ✅（⚠️ B1 数组/时间见 L-1/L-2） |
| 自审计 SA-1~SA-4 | ASCII 9 包重组、短包降级、畸形分包不抛、计数同步 | ✅ |

**福建基线 0x36 帧改判说明**：该帧是真实多包图片报（SYN）首包，v1.4.2 前基线断言的 2 要素实为「部分数据」输出；L-3 后改为 0 要素 + warning 是更诚实的行为。`feed()` 对该帧正确等待其余包（errors=[]）。建议：在示例文件标注该帧为多包样本；后续拿到完整多包语料时用 `feed()` 补端到端要素级断言。

---

## 六、缺陷汇总表

| 编号 | 严重度 | 文件:行 | 简述 | 状态 |
|------|--------|---------|------|------|
| M-1 | Medium | `sl651/constants.py:376`、`sl651/decoder.py _parse_ascii_elements` | ASCII 表键 `pH`（规约修正）与查找路径 `code.upper()` 断链，pH 要素名称/单位丢失；fixture 测试直查表键测不出 | 🆕 回归 |
| M-2 | Medium | `sl427/decoder.py:989,1364`、`sl651/bcd.py:13` | DIV 重组直接解析绕过 `decode()` 异常包装，非法 BCD `ValueError` 从 `feed()` 裸泄漏（变异 5% 触发）；v1.2.5 H 级缺陷复活；fuzz 套件无 DIV 分支 | 🆕 回归 |
| L-1 | Low | `sl427/decoder.py` B1 分支 | 多记录 rest 静默截断（12 条只出 1 条）无 warning | 🆕 |
| L-2 | Low | `sl427/decoder.py` B1 起止时间 | 合法 BCD 越界日历值（时 30/月 23）照常显示 | 🆕 |
| L-3→Info | Info（文档） | `tests/test_constants_spec.py:96` docstring | 「PDF 表 C.1 快照」表述与实际不符（名称列为工具显示口径；fixture 文件本身无此句）；映射/单位经独立 diff 验证无语义错误 | 🆕 文档说明 |

---

## 七、审计师评估与建议

1. **修复优先级**（复核同意）：M-2 > M-1 > L-1 > L-2（L-3 为 Info 文档说明）。M-2 是公共 API 契约破坏；修复须按 §三 的单点受保护入口方案（覆盖 B0/84/B1 全部直接解析路径、不吞 DecodeError、不静默丢消息），不是单点 try/except；M-1 须用单点 casefold 查找（两分支方案经验证不完整）。
2. **两条横向规律的又一次验证**（连续四轮成立）：M-1/M-2 都是「同一语义两处实现」——表键规范化 vs 查找规范化、旧入口的异常保护 vs 新入口裸奔。建议把「新入口必须复用旧入口的保护/规范化函数」写进 fix 验收清单。
3. **测试盲区两项**：变异套件无 SL427 DIV 分支（M-2 根因之一）；fixture 测试不经运行时查找路径（M-1 根因之一）。两者的补测成本都很低。
4. **正面确认**：16 位 SYN 状态机在 4500 帧变异（含乱序/增量/坏 CRC/超大长度）下零未控异常；fixture 行级断言的价值在本轮被反证——它防住了方案笔误（58H=WP1）却没覆盖查找路径，说明「表基线测试必须穿透运行时入口」。
5. **方法论**：本轮新增「fixture ↔ 规约文本全量独立 diff」与「8000 帧定向变异」，前者可固化为 fixture 生成脚本的一部分（生成时自动比对，双源一致才入库）。

---

## 八、复现附注

（Python 3.10+，`sl651-toolkit` 加入 `sys.path`）

- **M-1**：`SL651Encoder(station_type=0x4B).build_ascii_frame([("pH","7.2")])` → `SL651Decoder().decode_hex(...)` → `[PH] 未知(pH)`；`SL651_ASCII_ELEMENTS.get("PH") is None` 而键 `"pH"` 存在。
- **M-2**：`payload=bytes.fromhex("dc17f01bf2e5dfb14175377d0f1c6724cd97c9154fe4808ba782cd892b67252ddd167b492382")`，按 B1/func=0x08 分 3 片（DIVS=3/2/1）构造 68H 帧，`SL427Decoder().feed(...)` → `ValueError: 无效 BCD 字节: 0x7D`（栈经 `_decode_div_reassembled:989`）。
- **L-1**：B1 帧 D = 9B 表48 头 + 12×3B 雨量记录 → 仅 1 条「雨量」，无 warning。
- **L-2**：B1 起止时间字节 `30 24 01 02` → 显示「2002-01-24 30:00」。
- **L-3**：`python /tmp 比对脚本`（guide→ASCII 精确 + 名称/单位分类），或对照 `行业规范/水文监测数据通信规约SL651-2014.txt` 行 4046（38H VT 电源电压）。
- **变异**：8000 帧（bin_syn 3000 / stream_syn 1500 / ascii_syn 1500 / div427 2000，seed=20261105）→ 395 个未控异常全部 div427。

> 本报告只审不修，未修改任何源码、测试或既有文档；所有结论均可由上述构造方式复现。

---

## 九、对抗复核采纳记录（2026-11-05，依 `audit_review_v2.8.md`）

复核确认 M-1/M-2 实锤、无法推翻；以下四处修订已验证采纳，正文已同步改写：

1. **M-1 修复方案升级**：原「`get(code) or get(code.upper())` 两分支」经实测不完整——`PH`/`ph` 令牌两种写法下均未命中（复核方判断正确）。已改为单点 `casefold` 索引/`_lookup_ascii()` 方案，并把多值收集处列为同一处修复、不变量测试改为穿透查找入口。
2. **M-2 措辞收敛**：①「v1.2.5 H 级复活」明确标注为谱系类比，本轮按当前影响（仅 DIV 路径、仅畸形输入、抛异常而非静默错值）定级 Medium；②「≈5% 触发率」限定为本次变异配置（seed=20261105、特定分布）下的数值，非现场误码率；③ 修复方案明确为覆盖 B0/84/B1 全部直接解析路径的单点受保护入口，不得吞 `DecodeError`、不得无提示丢弃整条重组消息。
3. **L-1 修复前置条件补充**：`_parse_ctrl_func_data` 不返回消费字节数，直接「rest 非空即 warning」会对合法多值误报；修复须先返回 `(elements, consumed)` 或按 `func_code` 计算记录数。示例已标注 func=0x01。
4. **L-3 重新定位并降级 Info**：「PDF 表 C.1 快照」字样经核验在 `test_constants_spec.py:96` 的 docstring，fixture 文件内无此句（原报告定位不准）；该句与名称列为工具显示口径的事实不符，属文档说明级，已从 L 降为 Info 并修正定位。fixture 数据本身（映射 131/131、单位全对）经本轮独立 diff 确认可信。

优先级维持：**M-2 > M-1 > L-1 > L-2**（L-3 为 Info）。复核与审计双方对两个 Medium 的存在性、定级与修复方向一致。
