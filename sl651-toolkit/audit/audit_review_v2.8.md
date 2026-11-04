# v2.8 审计报告对抗性复核

> 复核日期：2026-11-05  
> 复核对象：`audit/audit_report_v2.8.md`（基线 `fcdeb9f`，v1.4.2）  
> 复核角色：主会话独立复核（只审不修）  
> 结论：**M-1、M-2 均实锤，无法推翻；L-1、L-2 成立；L-3 的结论成立但定位/表述不准确，应降为文档说明/Info。** 可抗辩的是定性措辞与修复建议的精确性，不是两个 Medium 的存在性。

---

## 一、独立复现结果

| 项 | 复核 | 结果 |
|---|---|---|
| M-1 pH 断链 | `build_ascii_frame([("pH","7.2")])` → `[PH] 未知(pH)=7.2` | ✅ 实锤 |
| M-2 DIV 异常泄漏 | B1/func=0x08 三片含非法 BCD → `feed()` 裸 `ValueError: 无效 BCD 字节: 0x7D` | ✅ 实锤 |
| L-1 B1 多记录 | 9B 头 + 12×3B 记录 → 只输出首条，余 33B 无 warning | ✅ 成立（具体示例类型需核对） |
| L-2 B1 时间越界 | `30 24 01 02` → `2002-01-24 30:00` | ✅ 成立 |
| L-3 fixture | fixture 映射 131/131 正确；名称 49 处为显示名 | ⚠️ 结论成立，定位不准 |

---

## 二、M-1：成立，但修复建议不完整

**不能抗辩的点**：`SL651_ASCII_ELEMENTS["pH"]` 存在、`["PH"]` 不存在，而 `_parse_ascii_elements` 用 `code.upper()` 查表；报文 `pH` 被转成 `PH` 后查不到。实测名称/单位丢失。

**可以抗辩/收窄的点**：

1. 报告建议 `entry = get(code) or get(code.upper())`：
   - 对规约的 `pH` 有效；
   - 对历史/厂商的 `PH` 仍无效（`get("PH")` 与 `get("PH".upper())` 都是 None）。
   - 若要真正“大小写兼容”，`get(code) or get(code.lower()) or get(code.upper())` 仍不够：
     表键是混合大小写 `pH`，`PH`/`ph` 都会漏。应建立一次性的 `{k.casefold(): (k, v)}` 索引，
     或写单点 `_lookup_ascii()`，查 `code.casefold()`；不要只写两个分支。
2. 多值收集处的 `nxt.upper()` 同样要改；报告已提到，但修复清单应把它列为**同一处修复**，否则 `pH` 作为后续 token 时行为仍不一致。
3. 建议补的不变量测试不应只测“表键存在”，而应直接调用 `_parse_ascii_elements` 或抽取的 `_lookup_ascii(code)`：**对表中每个 key，lookup(key) 必须命中**；这才是防止“表键 vs 查找”再次分裂的测试。
4. 定级 Medium 合理：名称/单位丢失、数值仍在，未造成数值错读；不应升 High，也不宜降 Low（水质核心要素）。

---

## 三、M-2：成立，但“H 级复活”与“5% 触发率”需加限定

**不能抗辩的点**：`_decode_div_reassembled` 直接 `_parse_data_field`，绕过 `decode()` 的 `except (ValueError, IndexError)`；`feed()` 对畸形分片裸抛，违反受控异常契约。复现栈与报告一致。

**可以抗辩/收窄的点**：

1. **“v1.2.5 H 级历史缺陷复活”是历史类比，不是本轮独立定级依据**。本轮应按当前影响定级：仅 DIV 重组路径、仅畸形 BCD/数据、异常而非静默错值，**Medium 合适**；把它称为 H 级复活容易高估。
2. **395/8000 ≈5% 是特定 fuzzer/种子/分布的触发率**，不是现场误码率；报告应写“该变异配置下”，不要被读成“5% 的真实报文会崩”。
3. “一行 try/except”不是完整修复：
   - 需要统一受保护入口，把 `ValueError/IndexError` 转为 `DecodeError` 或降级原始摘要 + warning；
   - B0/84/B1 三条直接解析路径都要覆盖，不能只包 B1；
   - 不应吞掉 `DecodeError` 或把整个重组消息无提示丢弃。
4. 变异套件补 DIV 分支是根因修复；报告这点是对的。

---

## 四、L-1/L-2：成立，但 L-1 的修复建议要先解决“consumed”信息

- L-1 的“静默截断”成立：`_parse_ctrl_func_data` 只返回元素，不返回消费字节数；`_decode_div_reassembled` 无法仅凭 `rest` 判断“剩余未消费”是多少。若直接按 `rest` 非空就 warning，会对合法多值/多记录产生误报。
- 建议先把 `_parse_ctrl_func_data` 改为返回 `(elements, consumed)`，或在 B1 分支按 `func_code` 的记录长度计算 `record_count`，再决定 warning；否则修复建议不可直接落地。
- 报告里“12 条 3B 雨量记录”的示例需要核对 `func_code`：B1 的数据格式由控制域命令/类型决定，func 不同则记录长度不同；现象本身不受影响，但示例应标明 func。

- L-2 成立；BCD 合法但日历越界（时 30/月 23）仍显示，建议占位或 warning。Low 合理。

---

## 五、L-3：结论成立，但“fixture 自称 PDF 快照”不准确

- `tests/fixtures/sl651_table_c1.tsv` **没有**“PDF 快照”字样；它只有表头 `guide/ascii/...`，是一份回归基线。
- “PDF 表 C.1 快照”出现在 `tests/test_constants_spec.py:96` 的 docstring，不在 fixture 文件里。
- 49 处名称是工具显示名（如 38H 电池电压 vs 规约电源电压），这是**文档表述/测试 docstring**问题，不是 fixture 数据语义错误；报告自己已确认映射 131/131、单位正确。
- 因此 L-3 建议降为 **Info/文档说明**，并把位置改为 `test_constants_spec.py` docstring，而不是 fixture 文件；若要保留 Low，应明确“测试注释误导”，不要写成 fixture 自称。

---

## 六、总体意见

1. M-1、M-2 都是真实回归，必须修；报告的核心结论成立。
2. 修复优先级同意：M-2 > M-1 > L-1 > L-3 > L-2。
3. 需要修正报告措辞/建议的地方：
   - M-1 的 `get(code) or get(code.upper())` 不完整，改为单点规范化 lookup；
   - M-2 的“H 级复活”“5%”加限定，修复覆盖 B0/B1/84 全部直接解析路径；
   - L-1 先补 consumed/记录数，再谈 warning；
   - L-3 位置改为 test docstring，降为 Info/文档说明。
4. 本轮不修改源码/测试；仅复核。

> 复核脚本：`build_ascii_frame([("pH","7.2")])`；B1/func=0x08 三片非法 BCD；B1 9B 头 + 12×3B；B1 时间 `30 24 01 02`；fixture 131 行。
