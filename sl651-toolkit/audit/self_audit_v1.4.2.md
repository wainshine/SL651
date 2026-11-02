# v1.4.2 自审计报告

> 日期：2026-11-03  
> 基线：v1.4.2（v1.4.1 `44535d6` + v2.7 修复）  
> 范围：SL651/SL427 解码器、常量表、编码器、CLI、测试、文档  
> 方法：代码精读 + 构造性回放 + 全量套件 + 边界帧  
> 结论：**发现 3 个真实缺陷，均已修复并加测试；当前 `run_all.py` 11/11。**

---

## 一、发现并修复

### SA-1（高）：ASCII SYN 重组伪帧仍保留 SYN，导致时间头偏移

**位置**：`sl651/decoder.py::_decode_reassembled` ASCII 分支。

**问题**：重组 ASCII 时构造伪帧只复制首包前 24B，未把第 23 字节的 `SYN` 改回 `STX`。`_decode_new_ascii` 看到 `SYN` 后按 `syn_pad=6` 解析，把包头的 6 个 ASCII 字符当成时间头，报：

```
ASCII 正文时间头解析失败: non-hexadecimal number found in fromhex() arg at position 6
```

任何 ASCII 多包重组都会失败，9 包实测复现。

**修复**：伪帧复制后显式 `hdr[C.ASCII_STX_OFFSET] = C.STX`。  
**测试**：`test_ascii_syn_reassembly_and_partial`，9 包 ASCII SYN 重组出 `Z=12.345`。

---

### SA-2（中）：ASCII SYN 分包帧在 `decode()` 中被“太短”提前拒绝，L-3 降级未生效

**位置**：`sl651/decoder.py::_decode_new_ascii` 入口长度检查。

**问题**：入口原检查 `total < ASCII_DATA_OFFSET + 3`（43B），而一个合法的 ASCII SYN 分包可能只有 38B（24B 头 + 6B 包头 + 3B 正文 + ETX/CRC）。结果在进入 L-3 判定前就抛 `ASCII 报文太短: 38 字节`，没有返回空要素 + warning。

**修复**：入口只要求至少到 `ASCII_STX_OFFSET`（24B），后续按实际 `body_len`/ETX/CRC 校验；SYN 的 `syn_pad=6` 只在 `stx==SYN` 时启用。  
**测试**：`decode(ASCII SYN 首包)` 返回空要素 + `SYN 分包帧…` warning；`total==1` 的 ASCII SYN 仍能解析出要素。

---

### SA-3（中）：L-3 先解析正文再清空，畸形分包可能抛异常

**位置**：`sl651/decoder.py::_decode_binary` / `_decode_new_ascii`。

**问题**：原实现先调用 `_parse_elements` / `_parse_ascii_elements`，再把 `elements` 清空。若分包正文是截断的非法 BCD/元素，解析阶段可能先抛 `DecodeError`，L-3 的“安全降级”不成立。

**修复**：当 `syn_total > 1` 时**直接跳过正文解析**，只保留报头元数据、CRC 和 warning；`feed()` 重组路径不受影响。  
**测试**：构造 `total=2, seq=1`、正文 `FF FF FF` 的 SYN 包，`decode()` 返回 0 要素 + warning，不抛异常。

---

### SA-4（中）：ASCII `pH` 被写成 `PH`

**位置**：`sl651/constants.py::SL651_ASCII_ELEMENTS`。

**问题**：表 C.1 的 46H ASCII 标识符是 `pH`（小写 p），实现写成 `PH`。因 ASCII 标识符大小写敏感，按规约 `pH` 编码的帧无法命中该表项。该问题在生成 131 行 TSV 逐行基线时暴露。

**修复**：键改为 `pH`；`test_constants_spec.py` 断言 `pH` 存在、`PH` 不存在；TSV fixture 同步。
**测试**：131 行 fixture 逐行比对通过。

### SA-5（低）：测试组数/文档计数漂移

新增测试后实际为：多包 12 组、SL427 分帧 14 组、协议契约 15 组、常量 5 组；README/project/handoff/fix_report 已同步为 11 套件及对应组数；并补 131 行 TSV fixture。

---

## 二、复核通过项

| 项 | 结果 |
|---|---|
| 表 C.1 58H~75H + FDH | 132 键；`WP1~WP8`、`SYL1~8`、`SBL1~8`、`VTA~VTC`、`VIA~VIC`、`DATA` 全在 |
| ASCII 130 字面键 | `NS/SQ/SW/ZT` 正确；`SD/MT` 不存在；`DRxnn` 动态 |
| 表 G.1 独立 | `SD/SDS/SQS/SWD` 等只在 G 表 |
| 5003B 单包 SYN | `feed()`/`decode()` 均可解析 |
| 5050B 两包 SYN | `feed()` 重组成功；不再 `>4095` |
| 300B SL427 DIV | 直接解析；不再 `>255` |
| B1 | 9B 表48 头 + `func_code` 分派；测试通过 |
| 84 超长 | warning + 前 2B 电压 |
| ASCII 分类码 | 编码 `K`、解码 `K`=水库，兼容 `4B` |
| ASCII SYN 包号 | `00A001` 10 包按 HEX 入缓存/重组 |
| ASCII 分类码 `pH` 大小写 | `pH` 命中；`PH` 不存在 |
| 131 行 TSV fixture | 逐行通过；覆盖旧 2 字符 HEX warning |
| YAML center/password | 字符串/越界返回可读错误，不裸栈 |
| 0x26 | N(6,1) 文档一致 |

---

## 三、残余

1. **表 G.1 仅核心 12 码**：完整 G.1（142 行）尚未全量落表；普通 ASCII 正文不使用 G 表，当前不影响 C.1 路径。
2. **B1 多记录数组**：后续数据按 `func_code` 做标量/单组解析；B1 一次返回多条记录时的数组展开可后续增强。
3. **下行 SYN 重组**：当前主要覆盖上行 M3；表23 下行 SYN 的分片重组未构造专项用例。
4. **重组 `body_length` 语义**：SL651 重组的 `body_length` 为合并后的正文长度（不含 3B SYN 包头），与单帧直解的 `body_length` 存在 3B 差异；已在修复报告记录，未改变字段类型。
5. **重组 CRC 展示**：`crc_received/calculated` 为 0，`crc_ok=True`，由 warning 说明“各分包 CRC 已逐包校验”。
6. **83/61 图片 `L×1K`**：维持 v1.4.1 保守降级，未纳入本轮。

---

## 四、验证

```text
python3 -B tests/run_all.py
→ 11/11 套件通过
```

真实语料：

- 福建 23 条、北京 25 条：CRC + 要素级基线通过；
- 单包 5003B、两包 5050B、SL427 300B、B1、84、ASCII 9 包、YAML 字符串均通过专项用例。

> 本轮自审计修复只改源码/测试/文档，未执行 `git add/commit`。
