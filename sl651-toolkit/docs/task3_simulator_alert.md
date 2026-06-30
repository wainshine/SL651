# 任务 3：模拟器加报机制

## 职责边界

在现有 `simulator/` 中增加加报触发逻辑，让雨量站和水位站在特定条件下自动发送加报帧（功能码 0x33）。

**不需要做**：
- 不需要修改协议编解码代码（sl651/、sl427/）
- 不需要读 PDF 规格文档
- 不需要改 Web UI

## 背景知识

### 当前模拟器架构

```
StationRunner（engine.py）
  └── 每 interval 秒循环：
      1. station.generate_elements()  → 生成要素数据
      2. encoder.build_timing_frame(elements, obs_time, function_code=0x32)  → 编码
      3. sender.send(hex_msg)  → 发送
```

**关键点**：当前 `build_timing_frame` 的 `function_code` 参数默认是 `0x32`（定时报）。改为 `0x33` 就是加报——帧结构完全一样，仅功能码不同。

### 雨量站（RainStation）

`RainGenerator` 有两个相关属性：

```python
gen = RainGenerator()
gen.raining          # bool: 当前是否在降雨
gen.rain_intensity   # float: 当前降雨强度 mm/min
```

`is_raining` 属性在 `RainStation` 上暴露：
```python
# 在 rain_station.py 中（需要确认是否已暴露，如果没有需要加一个 property）
```

### 水位站（WaterLevelStation）

`WaterLevelGenerator` 有一个历史值：
```python
gen.current   # 上一个时刻的水位值和当前值
```

加报逻辑：当前水位与上一次上报时的水位差值超过阈值时触发。

## 要读的文件

| 文件 | 读什么 |
|------|--------|
| `simulator/base_station.py` | `BaseStation` 基类，`generate_elements()` 签名 |
| `simulator/generators.py` | `RainGenerator` 的 `is_raining`/`rain_intensity`；`WaterLevelGenerator` 的 `current` |
| `simulator/water_level_station.py` | 现有水位站实现 |
| `simulator/rain_station.py` | 现有雨量站实现 |
| `simulator/engine.py` | `StationRunner` 类、`_run_station` 循环、`add_station` |
| `simulator/sender.py` | `Sender.send()` 接口 |
| `tools/simulate_cli.py` | 命令行参数定义 |
| `sl651/encoder.py` | `SL651Encoder.build_timing_frame` 的参数签名 |

## 具体要做的事

### 1. 在 RainStation 暴露 `is_raining` 属性（如果还没有）

```python
# simulator/rain_station.py
@property
def is_raining(self) -> bool:
    return self.rain_gen.raining
```

### 2. 在 WaterLevelStation 增加水位变化追踪

```python
# simulator/water_level_station.py
def __init__(self, ...):
    ...
    self._last_report_level = None  # 上次生成加报时的水位

def check_alert_trigger(self, threshold: float = 0.05) -> bool:
    """水位变化是否超过阈值（米）。"""
    current = self.water_gen.current
    if self._last_report_level is None:
        self._last_report_level = current
        return False
    if abs(current - self._last_report_level) >= threshold:
        self._last_report_level = current
        return True
    return False
```

### 3. 在 StationRunner 增加加报发送逻辑

修改 `engine.py` 的 `_run_station` 方法：

```python
def _run_station(self, runner: StationRunner) -> None:
    """单个站点的上报循环。"""
    while not runner._stop.is_set():
        try:
            now = datetime.now()
            elements = runner.station.generate_elements()
            
            # 定时报
            frame = runner.encoder.build_timing_frame(elements, obs_time=now, function_code=runner.function_code)
            hex_msg = frame.hex().upper()
            ok = runner.sender.send(hex_msg, runner.station.station_addr)
            
            # 加报判断
            if runner.enable_alert:
                triggered = False
                # 雨量站：正在下雨
                if hasattr(runner.station, 'is_raining') and runner.station.is_raining:
                    triggered = True
                # 水位站：水位变化超阈值
                if hasattr(runner.station, 'check_alert_trigger'):
                    triggered = runner.station.check_alert_trigger(runner.alert_threshold)
                
                if triggered:
                    alert_frame = runner.encoder.build_timing_frame(elements, obs_time=now, function_code=0x33)
                    runner.sender.send(alert_frame.hex().upper(), runner.station.station_addr)
            
            runner.station.advance(int(runner.interval / 60) or 1)
        except Exception:
            logger.exception("...")
        runner._stop.wait(runner.interval)
```

### 4. 修改 StationRunner 和 add_station 增加加报参数

```python
@dataclass
class StationRunner:
    station: BaseStation
    encoder: SL651Encoder
    sender: Sender
    interval: float = 300.0
    function_code: int = 0x32
    enable_alert: bool = False         # 新增
    alert_threshold: float = 0.05      # 新增（水位站用, 米）
```

`SimulatorEngine.add_station()` 增加对应参数。

### 5. 更新 CLI（simulate_cli.py）

增加参数：

```python
parser.add_argument("--enable-alert", action="store_true", default=False,
                    help="启用加报（雨量站下雨时/水位站越限时发送0x33帧）")
parser.add_argument("--alert-threshold", type=float, default=0.05,
                    help="水位站加报阈值，米 (默认 0.05)")
```

传给 `engine.add_station()` 时传入。

## 验收标准

```bash
# 雨量站加报：
python tools/simulate_cli.py --type rain --addr 1234567890 \
    --proto mqtt --broker 127.0.0.1:1883 --enable-alert --interval 30 -v

# 预期输出（verbose 模式）：雨量站降雨时能看到 "已发送...功能码=0x33"
```

用 Python 直接验证（不需要 MQTT broker）：

```python
from simulator import RainStation, WaterLevelStation
from simulator.sender import MqttxSender  # 不会被实际调用
from sl651 import SL651Encoder, SL651Decoder

# 雨量站——手动设置降雨状态
rs = RainStation("1234567890")
rs.rain_gen.raining = True
rs.rain_gen.rain_intensity = 0.5
elements = rs.generate_elements()

enc = SL651Encoder(center_addr=1, station_addr="1234567890", password=0, station_type=0x50)
frame = enc.build_timing_frame(elements, function_code=0x33)  # 加报
r = SL651Decoder().decode(frame)
assert r.crc_ok and r.function_code == 0x33

# 水位站——手动设置水位变化
ws = WaterLevelStation("1234567890")
ws.water_gen.current = 5.0
ws._last_report_level = 4.9
assert ws.check_alert_trigger(threshold=0.05)  # 0.1 > 0.05, 应触发
```
