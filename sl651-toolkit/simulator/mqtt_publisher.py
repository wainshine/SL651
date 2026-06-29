"""MQTT 发布器。

将 SL651 报文通过 MQTT 协议推送到服务器。支持：
- 普通 MQTT 发布（payload 为 SL651 二进制帧）
- 兼容 MQTTX 等工具订阅查看
- 多设备并发模拟
- 定时上报 / 加报触发
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from sl651 import bytes_to_hex_compact

from .base_station import BaseStation

logger = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    """MQTT 连接配置。"""

    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id_prefix: str = "sl651-sim"
    keepalive: int = 60
    # topic 模板，{station_addr} 会被替换为站点地址
    topic_template: str = "sl651/{station_addr}/uplink"
    # 是否同时发布 hex 字符串版本（便于 MQTTX 查看）
    publish_hex_also: bool = True
    # hex 版本的 topic 后缀
    hex_topic_suffix: str = "/hex"


class MqttPublisher:
    """MQTT 发布器。

    封装 paho-mqtt 客户端，提供 SL651 报文发布能力。

    用法::

        publisher = MqttPublisher(MqttConfig(host="broker.example.com"))
        publisher.start()
        publisher.publish_frame(station, frame_bytes)
        publisher.stop()
    """

    def __init__(self, config: MqttConfig) -> None:
        self.config = config
        self._client = None
        self._connected = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动 MQTT 客户端并连接。"""
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "未安装 paho-mqtt，请执行: pip install paho-mqtt"
            ) from e

        client_id = f"{self.config.client_id_prefix}-{int(time.time())}"
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish

        logger.info("正在连接 MQTT 服务器 %s:%d ...", self.config.host, self.config.port)
        self._client.connect(self.config.host, self.config.port, self.config.keepalive)
        self._client.loop_start()

        # 等待连接建立
        for _ in range(50):
            if self._connected:
                break
            time.sleep(0.1)
        if not self._connected:
            logger.warning("MQTT 连接尚未建立，将继续尝试后台连接")

    def stop(self) -> None:
        """停止 MQTT 客户端。"""
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None
        self._connected = False
        logger.info("MQTT 客户端已停止")

    def publish_frame(
        self,
        station: BaseStation,
        frame: bytes,
        message_type: str = "A1",
        qos: int = 0,
    ) -> None:
        """发布一帧 SL651 报文。

        Args:
            station: 设备实例（用于获取地址构造 topic）
            frame: SL651 二进制帧
            message_type: 报文类型（仅用于日志）
            qos: MQTT QoS 级别
        """
        if self._client is None or not self._connected:
            logger.warning("MQTT 未连接，跳过发布")
            return

        topic = self.config.topic_template.format(station_addr=station.station_addr)
        with self._lock:
            # 发布二进制帧
            info = self._client.publish(topic, frame, qos=qos)
            logger.info(
                "[%s] 站点=%s 类型=%s 长度=%d -> topic=%s (mid=%d)",
                datetime.now().strftime("%H:%M:%S"),
                station.station_addr,
                message_type,
                len(frame),
                topic,
                info.mid,
            )

            # 同时发布 hex 版本（便于 MQTTX 订阅查看）
            if self.config.publish_hex_also:
                hex_topic = topic + self.config.hex_topic_suffix
                self._client.publish(hex_topic, bytes_to_hex_compact(frame), qos=qos)

    def publish_hex(self, station: BaseStation, hex_str: str, qos: int = 0) -> None:
        """直接发布十六进制字符串。"""
        if self._client is None or not self._connected:
            return
        topic = self.config.topic_template.format(station_addr=station.station_addr)
        topic += self.config.hex_topic_suffix
        self._client.publish(topic, hex_str, qos=qos)

    # ------------------------------------------------------------------
    # MQTT 回调
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            self._connected = True
            logger.info("MQTT 连接成功")
        else:
            logger.error("MQTT 连接失败，返回码: %d", rc)

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT 意外断开 (rc=%d)，将自动重连", rc)
        else:
            logger.info("MQTT 已断开")

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None) -> None:
        pass


@dataclass
class StationRunner:
    """单个站点的运行配置。"""

    station: BaseStation
    interval_seconds: float = 60.0  # 定时上报间隔
    enable_a2_alert: bool = True  # 是否启用加报（雨量站下雨时）
    a2_threshold: float = 0.5  # 加报触发阈值（雨强 mm/min）
    a2_cooldown: float = 30.0  # 加报冷却时间（秒）
    _last_a2_time: float = field(default=0.0, init=False)


class SimulatorEngine:
    """模拟器引擎。

    管理多个站点的定时上报循环。

    用法::

        engine = SimulatorEngine(publisher)
        engine.add_station(WaterLevelStation("0000000001"), interval=60)
        engine.add_station(RainStation("0000000002"), interval=60)
        engine.start()  # 阻塞运行
    """

    def __init__(self, publisher: MqttPublisher) -> None:
        self.publisher = publisher
        self.runners: list[StationRunner] = []
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def add_station(
        self,
        station: BaseStation,
        interval: float = 60.0,
        enable_a2_alert: bool = True,
        a2_threshold: float = 0.5,
    ) -> None:
        """添加一个站点。"""
        runner = StationRunner(
            station=station,
            interval_seconds=interval,
            enable_a2_alert=enable_a2_alert,
            a2_threshold=a2_threshold,
        )
        self.runners.append(runner)
        logger.info(
            "已添加 %s 站点 %s，上报间隔 %.0f 秒",
            station.name,
            station.station_addr,
            interval,
        )

    def start(self, daemon: bool = False) -> None:
        """启动所有站点的上报循环（阻塞）。"""
        if not self.publisher._connected and self.publisher._client is not None:
            pass  # 后台会自动重连
        self._stop_event.clear()
        for runner in self.runners:
            t = threading.Thread(
                target=self._run_station,
                args=(runner,),
                name=f"station-{runner.station.station_addr}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        logger.info("模拟器已启动，共 %d 个站点，按 Ctrl+C 停止", len(self.runners))
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在停止...")
            self.stop()

    def stop(self) -> None:
        """停止所有站点。"""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()

    def _run_station(self, runner: StationRunner) -> None:
        """单个站点的上报循环。"""
        station = runner.station
        logger.info("[%s] %s 上报循环启动", station.station_addr, station.name)

        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                # 构造 A1 定时自报帧
                frame = station.build_a1_frame(body_time=now)
                self.publisher.publish_frame(station, frame, "A1")
                station.advance(int(runner.interval_seconds / 60) or 1)

                # 加报判断（仅雨量站）
                if runner.enable_a2_alert and hasattr(station, "is_raining"):
                    if station.is_raining and self._should_alert(runner):
                        a2_frame = station.build_a2_frame(body_time=now)
                        self.publisher.publish_frame(station, a2_frame, "A2")
                        runner._last_a2_time = time.time()

            except Exception:
                logger.exception("[%s] 上报异常", station.station_addr)

            # 分段 sleep 以便快速响应停止信号
            slept = 0.0
            while slept < runner.interval_seconds and not self._stop_event.is_set():
                time.sleep(min(1.0, runner.interval_seconds - slept))
                slept += 1.0

    @staticmethod
    def _should_alert(runner: StationRunner) -> bool:
        """是否应该触发加报（冷却时间已过）。"""
        return time.time() - runner._last_a2_time >= runner.a2_cooldown
