"""设备数据生成器。

模拟水位、雨量、墒情等遥测站的数据变化，生成符合物理规律的随机值。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class WaterLevelGenerator:
    """水位数据生成器。

    模拟水位在基准值附近做布朗运动 + 正弦日周期波动。
    """

    base_level: float = 5.0  # 基准水位 (m)
    amplitude: float = 0.5  # 波动幅度 (m)
    noise: float = 0.05  # 随机噪声幅度 (m)
    current: float = field(init=False)

    def __post_init__(self) -> None:
        self.current = self.base_level

    def next(self, tick: int = 0) -> float:
        """生成下一个水位值。tick 为时间步进。"""
        # 正弦日周期（24 小时 = 1440 分钟）
        daily = self.amplitude * 0.5 * math.sin(2 * math.pi * tick / 1440)
        # 布朗运动
        self.current += random.gauss(0, self.noise)
        # 回归基准
        self.current += (self.base_level - self.current) * 0.01
        value = self.base_level + daily + (self.current - self.base_level)
        return round(max(0, value), 3)


@dataclass
class RainGenerator:
    """雨量数据生成器。

    模拟降雨事件：大部分时间无雨，偶尔有降雨过程。
    """

    raining: bool = False
    rain_intensity: float = 0.0  # mm/min
    rain_remaining_minutes: int = 0  # 当前降雨过程剩余分钟
    daily_accum: float = 0.0  # 日累计
    hourly_accum: float = 0.0  # 小时累计
    last_hour_tick: int = -1
    last_day_tick: int = -1

    def next(self, tick: int) -> tuple[float, float, float]:
        """生成 (日累计雨量, 小时雨量, 雨强)。

        tick 为从 0 开始的分钟序号。
        """
        # 日重置（每 1440 分钟）
        if self.last_day_tick < 0:
            self.last_day_tick = tick
        if tick - self.last_day_tick >= 1440:
            self.daily_accum = 0.0
            self.last_day_tick = tick

        # 小时重置
        if self.last_hour_tick < 0:
            self.last_hour_tick = tick
        if tick - self.last_hour_tick >= 60:
            self.hourly_accum = 0.0
            self.last_hour_tick = tick

        # 降雨状态机
        if not self.raining and random.random() < 0.05:
            self.raining = True
            self.rain_remaining_minutes = random.randint(10, 120)
            self.rain_intensity = random.uniform(0.05, 1.5)

        if self.raining:
            self.rain_remaining_minutes -= 1
            if self.rain_remaining_minutes <= 0:
                self.raining = False
                self.rain_intensity = 0.0
            # 强度小幅波动
            self.rain_intensity = max(0, self.rain_intensity + random.gauss(0, 0.05))

        increment = self.rain_intensity  # 每分钟增量
        self.daily_accum += increment
        self.hourly_accum += increment

        return (
            round(self.daily_accum, 1),
            round(self.hourly_accum, 1),
            round(self.rain_intensity, 2),
        )


@dataclass
class SoilMoistureGenerator:
    """墒情数据生成器。

    模拟多层土壤含水量和温度，含水量受降雨影响缓慢上升。
    """

    layers: list[float] = field(default_factory=lambda: [25.0, 28.0, 30.0, 32.0, 35.0, 38.0])
    temps: list[float] = field(default_factory=lambda: [22.0, 21.0, 20.0, 19.0, 18.0, 17.0])
    rain_influence: float = 0.0  # 降雨影响累积

    def add_rain(self, intensity: float) -> None:
        """注入降雨影响。"""
        self.rain_influence += intensity * 0.5

    def next(self) -> tuple[list[float], list[float]]:
        """返回 (各层含水量列表, 各层温度列表)。"""
        new_moisture = []
        for i, m in enumerate(self.layers):
            # 降雨影响逐层衰减
            influence = self.rain_influence * (0.8 ** i)
            # 缓慢回归
            target = 30.0 + i * 2
            m += (target - m) * 0.005 + influence * 0.01
            m += random.gauss(0, 0.1)
            m = max(0, min(60, m))
            new_moisture.append(round(m, 1))
        self.layers = new_moisture
        self.rain_influence *= 0.95  # 影响衰减

        new_temps = []
        for i, t in enumerate(self.temps):
            daily = 2 * math.sin(2 * math.pi * (i + 1) / 1440)
            t += random.gauss(0, 0.05) + daily * 0.001
            new_temps.append(round(t, 1))
        self.temps = new_temps

        return new_moisture, new_temps


@dataclass
class VoltageGenerator:
    """电源电压生成器。"""

    base: float = 12.6
    noise: float = 0.1
    current: float = field(init=False)

    def __post_init__(self) -> None:
        self.current = self.base

    def next(self) -> float:
        self.current += random.gauss(0, self.noise)
        self.current += (self.base - self.current) * 0.1
        return round(self.current, 2)
