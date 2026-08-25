# 审计报告 v2.1

> 审计日期：2026-08-26  
> 基线文档：`docs/project.md` v1.2.4、`README.md` v1.2.4  
> 基准代码：v1.2.4（25 项测试通过）  
> 修复版本：**v1.2.5**（37 项测试通过）

---

## 一、审计范围与方法

三路并行只读审计，所有问题均经实际构造输入复现验证：

1. SL651 核心（decoder/encoder/bcd/crc/constants）
2. SL427 核心 + simulator 全部 + simulate_cli
3. tools CLI + web/app.py（v1.2.4 重写版）+ 测试 + 文档一致性

## 二、缺陷统计与修复状态

| 严重度 | 数量 | 状态 |
|--------|------|------|
| 高 | 4 | ✅ 全部修复 |
| 中 | 12 | ✅ 全部修复 |
| 低 | 20+ | ✅ 主要项修复（装饰性项保留） |

## 三、高危缺陷（已修复）

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| H1 | `sl651/decoder.py:406` | 截断上行帧 F1F1 探测越界抛 `IndexError`（body_len 可伪造） | F1F0 探测前加 `f0_pos+1 < etx_pos` 边界检查，走 fallback 分支 |
| H2 | `sl427/decoder.py:284` 等 | 地址域/数据域非法 BCD 泄漏 `ValueError`（所有帧必经路径） | `decode()` 外包 `try/except (ValueError, IndexError)` → `DecodeError` |
| H3 | `sl427/decoder.py:337` | 缺最小 L 校验，L=5/6 帧解码出垃圾（AFN 读到 CRC 字节） | `data_len < (8 if div else 7)` 抛 `DecodeError` |
| H4 | `simulator/sender.py` + `engine.py` | 多站点共享 `TcpSender` 无锁：帧字节交错 + socket 泄漏 | 加 `threading.Lock`，`_ensure_connected`+`sendall` 全程持锁；失败路径先 close 再置 None |

## 四、中危缺陷（已修复）

### SL651
| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| M1 | `decoder.py:528` | Hex 型要素（f3 图片等）首字节 0xFF 被误判负数前缀（65296KB→-16） | `is_neg` 仅 BCD 分支生效 |
| M2 | `decoder.py:301` | ASCII 帧 CRC 4 字符非 hex 时 `ValueError` 逃逸；`crc_raw` 死变量 | 纳入 try/except → `DecodeError`；删死变量 |
| M3 | `decoder.py:635` | ASCII ST 段站类 token 非 hex 时 `ValueError` 逃逸 | try/except 降级为「未知」 |
| M4 | `encoder.py:19` | `_make_def_byte` 超范围静默掩码截断，自产畸形帧 | 超范围抛 `EncodeError` |
| M5 | `encoder.py:269` | 小时报水位 >655.35m 抛裸 `OverflowError` | 抛 `EncodeError` |

### SL427
| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| M6 | `encoder.py:23` | `encode_address` 无范围校验：stn_id 越界 `OverflowError`、method=3 静默、hex 非法字符 `ValueError` | 显式校验，统一 `EncodeError` |
| M7 | `encoder.py:88` | `build_frame` 无 L≤255 / Tp=7B / PW=2B 校验 | 超限抛 `EncodeError` |
| M8 | `encoder.py:19` | `_bcd_byte` 无 0~99 校验：year<2000 崩溃、≥2100 静默非法 BCD；delay 负数回绕 | `_bcd_byte`/`encode_tp` 范围校验 |
| M9 | `decoder.py:542` + `constants.py:136` | AFN=FFH：`AFN_TP_ONLY` 声明含 Tp 但解码不剥离，尾部 7B 被乱解析 | FF 分支剥离尾部 Tp 并单独展示 |

### 模拟器 / CLI
| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| M10 | `tools/simulate_cli.py` | YAML 零校验：空文件 `AttributeError`、未知 type `KeyError`、interval≤0 忙循环；`parse_host_port` TCP 模式默认 1883 | schema 校验 + 友好退出；默认端口按协议区分（MQTT 1883 / TCP 5001） |
| M11 | `simulator/generators.py:131` | 墒情温度正弦相位用层索引而非 tick，构成恒定漂移且无 clamp（数周后非物理值） | 相位改用 tick + 均值回归 + clamp(-30~60) |
| M12 | `simulator/engine.py:73` | 雨量加报电平触发：一次 2h 降雨连发 24 条 0x33 | 改边沿触发（`_alert_active` 状态位）；`SendError` 单独捕获终止 runner |

### Web / 输出
| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| M13 | `web/app.py:501` | `/api/decode` 非对象 JSON / 非字符串 hex → 500 | 类型校验 → 400 |
| M14 | `tools/decode_cli.py` JSON / `web/app.py` | JSON 输出与 Web 帧信息泄露完整密码（text 路径脱敏决策被绕过） | JSON `_sanitize_dict`（密码 ****，站址截断）；Web 密码显示 **** |

## 五、低危缺陷（已修复主要项）

| # | 位置 | 修复 |
|---|------|------|
| L1 | `web/app.py:427` HTML 结尾缺 `>` | 补全 |
| L2 | `web/app.py` crc_pill `null` 时显示空胶囊 | 改 `=== true/false` 判断 |
| L3 | `sl427/decoder.py` `to_dict` 缺 `frame_length`/`data_len` | 已补，Web/JSON 信息完整 |
| L4 | `tools/decode_cli.py:122` `--raw-only` 死参数 | 移除；`--hex`/`--file` 改互斥组 |
| L5 | `tools/decode_cli.py` 文件读取裸 traceback、tty 下阻塞 stdin | 友好报错 + `isatty()` 打印帮助 |
| L6 | `sl651/decoder.py:167` `_build_byte_map` 高亮分支全为死代码（offset 步进 16 永不命中 2/13/22/30） | 改按绝对下标判断 |
| L7 | `sl651/decoder.py:186` `_build_byte_table` 未计入 SYN 偏移 | 加 `syn_pad` 参数 |
| L8 | `sl651/decoder.py` ASCII 无要素时丢失 ST/TT 提取 | 改为无条件提取 |
| L9 | `sl651/decoder.py` f0/f1 引导符定义符不匹配时坠入 BCD 误解析 | 显式 break（流已失同步） |
| L10 | `sl651/encoder.py` `data_len=1` 负数编码出孤立 0xFF | 抛 `EncodeError` |
| L11 | `sl651/encoder.py` 构造参数静默掩码（center_addr=300→44） | 显式范围校验抛 `EncodeError` |
| L12 | `sl427/constants.py:158` `encode_pw` key1/key2 校验不完整 | 补 `0≤key1≤9`、`0≤key2≤999` |
| L13 | sl427 decoder/encoder 未使用 import（datetime 等） | 清理 |
| L14 | `simulator/base_station.py` 地址只查长度不查 hex | 补字符集校验 |
| L15 | `simulator/engine.py` stop 不 join 线程 | 补 join(timeout=2) |

### 保留项（不修）

| 项 | 原因 |
|----|------|
| `to_dict` 要素 value 含单位字符串（如 "12.345 m"） | 展示层契约，下游尚无机器消费方；unit 字段同时存在 |
| AFN=84H docstring/常量/行为三处表述差异 | 编解码各自可用，待实物验证后统一（同 handoff §3.3 A1 大端保留项） |
| 解码器对 CRC 错误帧继续解析 | 分析工具的有意设计 |
| ASCII 多值标注 `[1]` 起 | 装饰性 |

## 六、文档一致性修正（8 处）

| # | 位置 | 修正 |
|---|------|------|
| D1 | handoff_main ×2 / README / project | 测试数量 24 → 37 |
| D2 | README 目录树 | 补列 `test_round1_blindspots.py` |
| D3 | project.md:115 / handoff_main:49 | ASCII 标识符「161 项」→ 实测 102 项 |
| D4 | sl651/README.md:13 | 「140+ 项」→ 102 项；FUNC_MAP「13 项」→ 23 项 |
| D5 | sl427/README.md:11 / README.md:22 | AFN「32 项」→ 实测 30 项 |
| D6 | README.md:148 / sl651/README.md:78 | `build_query_frame(guides)` 签名错误 → 无参 + 补 `build_query_body` |
| D7 | README.md:51 | 审计报告范围 v1.1~v1.8 → v1.1~v2.1 |
| D8 | web/README.md:41 | flask「单独安装」→ 已含于 requirements.txt |

## 七、测试

- `tests/test_sl651.py`：25 → **37 项**，全部通过（新增 12 项回归：H1~H4、Hex 型 FF、两侧编码器校验、FFH Tp 剥离、Web API、CLI 脱敏、YAML 校验、温度有界、边沿触发）
- `tests/test_round1_blindspots.py`：10 项，全部通过
- 福建 23 条 / 北京 25 条真实报文 CRC 验证：全部通过（无回归）

## 八、结论

v1.2.5 修复了 4 项高危（异常契约破坏 + TCP 帧交错）与 12 项中危缺陷，库对畸形输入的行为统一为 `DecodeError`/`EncodeError`；Web 界面同步重写为亮色主题并补齐脱敏。未发现协议解析逻辑（CRC 覆盖、流水号规则、SYN 偏移、AUX 分离）层面的新错误。
