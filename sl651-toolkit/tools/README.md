# tools — CLI 命令行工具

## 概述

提供两个命令行工具：报文解码器 `decode_cli.py` 和 设备模拟器 `simulate_cli.py`。

## 文件清单

| 文件 | 说明 |
|------|------|
| `decode_cli.py` | SL651 / SL427 双协议报文解码 CLI |
| `simulate_cli.py` | SL651 设备模拟器 CLI |

## decode_cli — 报文解码器

### 命令格式

```bash
python tools/decode_cli.py {sl651|sl427} [--hex HEX] [--file FILE] [--output {text|json}]
```

### 选项

| 参数 | 说明 |
|------|------|
| `sl651` / `sl427` | 子命令，必选 |
| `--hex` | 十六进制报文字符串 |
| `--file`, `-f` | 报文文件（每行一条，`#` 开头为注释） |
| `--output`, `-o` | `text`（默认）或 `json` |
| 无参数 | 从 stdin 读取 |

### 使用示例

```bash
# SL651 解码（HEX/BCD 或 ASCII）
python tools/decode_cli.py sl651 --hex "7E7E2500418D233700..."

# SL427 解码
python tools/decode_cli.py sl427 --hex "681568B4..."

# 文件批量（含福建规定 23 条）
python tools/decode_cli.py sl651 --file examples/fujian_messages.txt

# JSON 输出
python tools/decode_cli.py sl651 --hex "7E7E..." -o json
```

### 输出字段

**SL651 text**：中心站地址、遥测站地址、密码、功能码、方向、正文长度、流水号、发报时间、测站类别、观测时间、编码方式、CRC 校验、要素列表

**SL427 text**：方向、控制功能码、地址、AFN、用户数据长度、CRC8 校验、要素列表

**JSON**：`{total, success, failed, results: [...], errors: [...]}`，每条 result 为 `to_dict()` 输出

## simulate_cli — 设备模拟器

### 命令格式

```bash
python tools/simulate_cli.py [--type TYPE] [--addr ADDR] [--proto {mqtt|sl651}]
      [--broker HOST:PORT] [--target HOST:PORT] [--topic TOPIC]
      [--center N] [--pwd N] [--interval SECONDS]
      [--enable-alert] [--alert-threshold METERS]
      [--config YAML] [-v]
```

### 选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--type` | `water_level` | 站点类型：`water_level` / `rain` / `soil` |
| `--addr` | `1234567890` | 遥测站地址（10 位 hex） |
| `--proto` | `mqtt` | 协议：`mqtt`(mqttx CLI) / `sl651`(TCP) |
| `--broker` | `127.0.0.1:1883` | MQTT broker 地址:端口 |
| `--target` | `127.0.0.1:5001` | TCP 目标地址:端口 |
| `--topic` | `sl651/{station_addr}/uplink` | MQTT topic 模板 |
| `--center` | `1` | 中心站地址 |
| `--pwd` | `0` | SL651 密码 |
| `--interval` | `300.0` | 上报间隔（秒） |
| `--enable-alert` | — | 启用加报 |
| `--alert-threshold` | `0.05` | 水位站加报阈值（米） |
| `--config` | — | YAML 多站点配置文件 |
| `-v` / `--verbose` | — | 详细日志 |

### 使用示例

```bash
# MQTT 模式 — 水位站每 5 分钟上报
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto mqtt --broker 192.168.1.100:1883 --interval 300

# TCP 模式 — 直连采集服务器
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto sl651 --target 192.168.1.100:5001

# 雨量站 + 加报
python tools/simulate_cli.py --type rain --addr 1234567892 \
    --proto mqtt --broker 127.0.0.1:1883 --enable-alert

# 多站点 YAML
python tools/simulate_cli.py --config examples/stations.yaml
```

## 依赖

- `sl651/` — 编解码器
- `sl427/` — SL427 解码器
- `simulator/` — 站点模拟器、发送器、引擎
- `PyYAML>=6.0`（YAML 配置可选）
