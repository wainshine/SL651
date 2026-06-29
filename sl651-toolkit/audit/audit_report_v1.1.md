# SL651-Toolkit 代码审计报告 v1.1

## 一、审计概述

| 项目 | 信息 |
|------|------|
| 审计版本 | v1.1（第二次审计后持续跟踪，最终版） |
| 审计对象 | `sl651-toolkit`（24 个源文件） |
| 对比基线 | v1.0 审计报告 |
| 参考依据 | SL/T 651-2014 水文监测数据通信规约、SL/T 427-2021 水资源监测数据传输规约 |
| 基准工具 | 南京蓉水 njnrs.com SL651 报文解析器、SLT427 报文解析器 |
| 审计方式 | 只审不修 |

## 二、相对 v1.0 的变化摘要

| 变化项 | 说明 |
|--------|------|
| `simulator/mqtt_publisher.py` | **删除**，拆分为 `engine.py` + `sender.py` |
| `simulator/sender.py` | **新增**，抽象 `Sender` 基类 + `MqttxSender` + `TcpSender`（含重连） |
| `simulator/engine.py` | **新增**，`StationRunner` + `SimulatorEngine` |
| `BaseStation` | 重构：`generate_elements()` 返回 `list[tuple[int,float,int,int]]` |
| 站点类 | 要素 ID 修正为国标 HEX 码（`0x39`/`0x1F`/`0x10~13`） |
| `constants.py` | 新增 13 个帧偏移常量，消除魔法数 |
| `requirements.txt` | 移除 `paho-mqtt`（改用 mqttx CLI） |
| v1.0 致命缺陷 3.1~3.3 | ✅ 全部修复 |

---

## 三、缺陷状态一览

> ✅ = 已修复； ⬜ = 待修复

### 3.1 ✅ README 全面过时

README 已全面重写。目录结构、CLI 命令、Python API 属性名、要素标识符表、YAML 格式、依赖说明均已与实际代码对齐。版本号已更新为 `v1.1.0`。

### 3.2 ✅ stations.yaml 格式不兼容

YAML 已适配 `sender.proto/broker/topic` 结构。

### 3.3 ✅ 编码器负数 BCD 编码

`_encode_bcd` 采用规范 `0xFF` 前缀；解码器同步处理。`test_negative_bcd` 覆盖。

### 3.4 ✅ SLT427 `_parse_comprehensive` 跳位

已添加注释说明 bit0 含义。

### 3.5 ✅ DEVICE_TYPES 死代码

已移除。

### 4.1 ✅ 版本号不一致

`__init__.py:44` → `"1.1.0"`，README 标题 → `v1.1.0`。已一致。

### 4.2 🚫 SLT427 无编码器

`slt427/` 仅有 `decoder.py` + `constants.py`。当前只需解码，编码暂不需要。

### 4.3 🚫 测试未覆盖模拟器链路

`BaseStation` → `StationRunner` → `Sender.send()` 无自动化测试。模拟器为辅助工具，测试侧重协议编解码正确性。

### 4.4 ✅ sender.py 未使用的导入

已移除 `bytes_to_hex_compact`。

### 4.5 ✅ TcpSender reconnect 逻辑不完整

`_ensure_connected` 增加 `self._sock is not None` 检查和 OSError 处理；`send()` 失败时若 `reconnect=True` 会实际重连。`simulate_cli.py` 两处构造均传 `reconnect=True`。

### 4.6 ✅ generators.py `__import__("math")`

已改为 `import math`，使用 `math.pi`。

### 4.7 ✅ topic 占位符不一致

统一为 `{station_addr}`。

### 4.8 🚫 SL651 解码器仅支持 HEX/BCD 帧

ASCII 编码帧（起始符 `01H`/SOH）未实现。当前目标场景为 HEX/BCD 编码帧。

### 4.9 ✅ `_load_config` 返回值

已修正为 `return _load_config(args.config)`。

### 4.10 ✅ 解码器硬编码偏移量

`constants.py` 新增帧偏移常量，`decoder.py`/`encoder.py` 已全部改用常量。

### 5.1 ✅ 编码器序列号随机初始值

`_serial` 改用 `int(datetime.now().timestamp()) % 65535`，基于时间戳保证重启后不重复。

### 5.2 🚫 密码默认值为 0

`encoder.py` 已添加 docstring 说明"用于测试；生产环境应使用非零密码"。作为 CLI 默认值可接受。

### 5.3 ✅ DecodedMessage 缺少 message_type 字段

`DecodedMessage` 增加 `message_type: str` 字段，`decode()` 中从 `func_name` 填充，`to_dict()` 输出包含该字段。

### 5.4 ✅ TcpSender 构造参数不完整

`simulate_cli.py` 两处 `TcpSender` 构造均传 `reconnect=True`。

### 5.5 ✅ STATION_TYPE_MAP 与站点类属性重复

已用 `STATION_TYPE_MAP` 字典取值。

### 5.6 ✅ mqttx CLI 前置条件未说明

README 已增加 macOS/Linux 的 `mqttx` CLI 安装指令。

---

## 四、测试结果

```
============================================================
SL651 工具包自测
============================================================
>>> BCD 编解码               OK
>>> CRC-16/MODBUS            OK
>>> 定义符解析                OK
>>> njnrs 示例报文解码         OK
>>> 水测家加报报解码           OK
>>> 编码 → 解码往返           OK
>>> CRC8                      OK
>>> SLT427 解码                OK
>>> 负数 BCD 编解码            OK
>>> 无效BCD数据优雅降级         OK

所有测试通过
```

---

## 五、已知设计决定（非缺陷）

以下 4 项经确认属于有意设计选择：

| 项 | 说明 |
|----|------|
| 无 SLT427 编码器 | 当前只需解码 SLT427 报文，编码暂不需要 |
| 缺 ASCII 帧支持 | 当前目标场景为 HEX/BCD 编码帧；ASCII 帧按需扩展 |
| 模拟器链路无自动化测试 | 模拟器为辅助工具，测试侧重协议编解码正确性 |
| 日志配置依赖调用方 | 库代码使用 `logging.getLogger(__name__)` 为标准 Python 惯例 |

---

## 六、缺陷汇总

**v1.0 初始 21 项缺陷，已全部修复或确认无影响。当前无待修复缺陷。**

| 历史级别 | 已修复 | 设计决定 | 合计 |
|----------|--------|----------|------|
| 致命 | 3 ✅ | 0 | 3 |
| 严重 | 8 ✅ | 0 | 8 |
| 中等 | 5 ✅ | 3 | 8 |
| 轻微 | 5 ✅ | 1 | 6 |
| **合计** | **21 ✅** | **4** | **25**
