# SL651-Toolkit v1.4.0 修复闭环报告（v1.4.1 勘误）

> 基线：v1.3.2 / git `5b02471`  
> 版本：v1.4.0（2026-11-02；v1.4.1 勘误 2026-11-02）
> 测试：`python3 -B tests/run_all.py` → **10/10 套件通过**；福建 23 条 / 北京 25 条 rc=0  
> 输入：`audit_report_v2.5.md`（4M+11L）、`audit_report_v2.6.md`（1M+8L）、v2.6 补充审计（L-12~L-17 + 1 潜伏）

## 一、结论

30 项待修 + 1 项潜伏观察全部处理；其中 **v2.5 M-4 经复现降为 Low**。规约证据链：§7.5.5（AFN=84 自报电压，类型码 1101B，D=2B）、§7.3.22 n)（B0 查询输入电压 2B+4B）、表 24 D12「报警或状态(监测终端机电压)」；§7.5.2b 明确 81 的 0x0D 无中间参数；§7.5.6 的 C0 自报条件不含电压，故 C0+0x0D 属规约未定义场景，按 §7.3.22 n 的 2B 电压作最一致解读。报告复现的 4B 帧与审计 B 的 15B D=4B 均非标准 D 长度，实现改为可观测降级。最终严重度口径为 **4M+26L**。

新增 2 个套件：`test_sl427_multiframe.py`（11 组）、`test_protocol_contracts.py`（12 组）；`test_sl651_multipacket.py` +3 组；`run_all.py` 8 → 10。

## 二、逐项闭环

### v2.5

| 编号 | 修复 | 验证 |
|---|---|---|
| M-1 | SYN 逐包 CRC；seq==1/总包数/同 seq 内容变化重置；坏包不入缓存 | `test_syn_corrupt_packet_rejected`；多包套件全过 |
| M-2 | 综合参数按位图定长切块，填充块输出 `-` 且不吞下一参数 | `test_comprehensive_and_fill` |
| M-3 | 缓存 64 组/8MB/TTL 300s；`errors`/`dropped_frames`；谎报长度重同步 | `test_pending_bounded`、`test_false_length_resync` |
| M-4（降 L） | 0x0D 上下文：B0/84/C0/82 电压（C0 为规约未定义场景的 2B 解读），81 无中间参数；短帧/异常 D 长度降级 | `test_0d_contexts` |
| L-1 | 标量填充输出 `-` | `test_comprehensive_and_fill` |
| L-2 | 旧双 SOH 方言可 `feed()` | `test_legacy_ascii_feed_and_garbage_resync` |
| L-3 | F4 0~25.4 / F5 0~655.34，非法值抛 `EncodeError`；84 文案 0~99.99 | `test_hourly_bounds_and_def_byte` |
| L-4 | `sl651.errors` 共享异常类 | `test_exception_identity` |
| L-5 | YAML `function_code` 白名单 `{0x30,0x32,0x33}`、`alert_threshold` 校验 | `test_simulator_config_validators` |
| L-6 | SL427 `_warnings` 改为局部变量 | 代码审阅 + 全套件 |
| L-7 | CLI 原始报文/errors 默认脱敏 | `test_cli_masking` |
| L-8 | Mqttx 密码 argv 暴露 warning + README 说明 | 代码/文档 |
| L-9 | 年份 2000~2099 统一 `EncodeError` | `test_encoder_invalid_inputs` |
| L-10 | `direction` 仅 0/1 | `test_encoder_invalid_inputs` |
| L-11 | 前导垃圾同批重扫 | `test_legacy_ascii_feed_and_garbage_resync` |

### v2.6

| 编号 | 修复 | 验证 |
|---|---|---|
| M-1 | SL427 DIV=1 重组（B0/B1/84）；C0/81/82/FF 安全降级；83/61 因 L×1K 未证安全丢弃；`divs=` 编码 | `test_sl427_multiframe.py` |
| L-1 | `encode_address` 方式1 110000~829999，默认 110000 | `test_address_roundtrip` |
| L-2 | guide/NaN/inf 统一 `EncodeError`；mode/heartbeat 严格校验 | `test_encoder_invalid_inputs` |
| L-3 | 负水位/负雨量抛 `EncodeError` | `test_hourly_bounds_and_def_byte` |
| L-4 | JSON `errors[].message` 脱敏 | `test_cli_masking` |
| L-5 | A 补齐 BCD（仅 40H~43H；编码 `a_pad_guides=`） | `test_a_pad_bcd` |
| L-6 | 45H 按表60 4B/12 有效位，保留位非零写 `warnings` | `test_45h_reserved_bits` |
| L-7 | TcpSender 重连等待移出锁 | `test_tcp_sender_reconnect_sleep_outside_lock` |
| L-8 | 信道 0xAA/0xFF 均降级“无” | `test_comprehensive_and_fill` |

### v2.6 补充

| 编号 | 修复 | 验证 |
|---|---|---|
| L-12 | CLI 中心站地址整体遮 `**` | `test_cli_masking` |
| L-13 | `build_set_work_mode` 仅 0~3 | `test_encoder_invalid_inputs` |
| L-14 | 移除 `safe_bcd_to_int` 死导入 | 代码审阅 |
| L-15 | `_parse_status` docstring 改为表58 位定义 + 表60 4B | 代码/文档 |
| L-16 | 0x1F 上一日累计、0x20 当前日累计分离 | `test_simulator_integration` |
| L-17 | F5 定义符 0xC2 → 0xC0 | `test_hourly_bounds_and_def_byte` |
| 潜伏 | `_safe_hex_val` 全 F 误伤 0xFF 加注释，当前无活跃路径 | 代码注释 |

## 三、关键行为变更

- `SL651Decoder.feed()`/`SL427Decoder.feed()`：新增 `errors`、`dropped_frames`；SL427 新增 `feed()` 与 `build_frame(divs=)`。
- `SL427Decoder.decode()` 遇 DIV=1：空要素 + warning；`feed()` 默认不解析孤立 DIVS=1（`allow_single_div=True` 可开启）。
- `encode_address()` 默认 `admin_code` 0 → 110000；方式1 范围 110000~829999。
- `mode`/`heartbeat`/`guide`/`NaN`/`inf`/年份/方向等从静默掩码/裸异常改为 `EncodeError`。
- CLI 默认脱敏，`--show-raw` 显示完整报文。
- `45H` 4B 保留位非零写 warning（北京语料 2 条会出现该 warning）。

## 四、已知残余/非目标

1. **83/61 图片分帧**：§6.3.3.2b 的 `L×1K` 语义无真实样本确认，`feed()` 安全丢弃并记 error；待样本后启用。
2. **SL651 跨报文混组**：协议无报文 ID，极端丢包+交错仍可能混组；已用逐包 CRC/seq1/TTL/上限降低，文档化。
3. **Mqttx 长连接/paho**：v1.4.0 仅文档 + warning，paho 留 v1.5。
4. **Web 脱敏**：CLI 已默认脱敏；Web 本机调试界面未强制遮罩。


## 五、v1.4.1 勘误

| 项 | 修正 |
|---|---|
| SL427 81 分支 0x0D | `_parse_0d_payload("c0", ...)` → `afn_hex`；81 非空 D 不再误判电压，改为原始摘要 + warning；新增回归 |
| M-4 引证 | fix_report 改为 §7.5.5 / §7.3.22 n) / 表24 D12；明确 C0+0x0D 为规约未定义场景 |
| 孤立 DIVS=1 | 入组即写 warning；TTL 淘汰时把 warning 带入 error |
| SL651 重同步 | 识别 ENQ/EOT 结尾帧 |
| 测试 | 新增手工按表3 拼 B0 分帧、3 帧乱序 1/3/2、SL427 缓存上限/TTL、SL427 CLI 地址脱敏 |
| CLI | SL427 `addr` text/JSON 统一遮蔽（方式标签保留） |
| 自审计 | A 补齐 warning 仅在成功解码时输出；短帧缺 Tp 文案；每 64 帧淘汰缓存；ACK/NAK/ESC 重同步 |
| 版本 | 1.4.0 → 1.4.1 |
