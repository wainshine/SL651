"""模拟器定时循环引擎。"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from sl651 import SL651Encoder

from .base_station import BaseStation
from .sender import Sender

logger = logging.getLogger(__name__)


class StationRunner:
    """单个站点的运行配置。"""

    def __init__(
        self,
        station: BaseStation,
        encoder: SL651Encoder,
        sender: Sender,
        interval: float = 300.0,
        function_code: int = 0x32,
        enable_alert: bool = False,
        alert_threshold: float = 0.05,
    ):
        self.station = station
        self.encoder = encoder
        self.sender = sender
        self.interval = interval
        self.function_code = function_code
        self.enable_alert = enable_alert
        self.alert_threshold = alert_threshold
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"sim-{self.station.station_addr}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        logger.info("[%s] %s 启动, 间隔 %ds, 加报=%s",
                     self.station.station_addr, self.station.name, self.interval,
                     "开启" if self.enable_alert else "关闭")
        while not self._stop.is_set():
            try:
                now = datetime.now()
                elements = self.station.generate_elements()
                frame = self.encoder.build_timing_frame(
                    elements, obs_time=now, function_code=self.function_code,
                )
                hex_msg = frame.hex().upper()
                ok = self.sender.send(hex_msg, self.station.station_addr)
                if ok:
                    logger.info("[%s] 已发送 %s 功能码=0x%02X (%dB)",
                                 self.station.station_addr,
                                 now.strftime("%H:%M:%S"),
                                 self.function_code,
                                 len(frame))

                if self.enable_alert:
                    triggered = False
                    if hasattr(self.station, 'is_raining') and self.station.is_raining:
                        triggered = True
                    if hasattr(self.station, 'check_alert_trigger'):
                        triggered = self.station.check_alert_trigger(self.alert_threshold)

                    if triggered:
                        alert_frame = self.encoder.build_timing_frame(
                            elements, obs_time=now, function_code=0x33,
                        )
                        alert_hex = alert_frame.hex().upper()
                        ok_alert = self.sender.send(alert_hex, self.station.station_addr)
                        if ok_alert:
                            logger.info("[%s] 已发送加报 %s 功能码=0x33 (%dB)",
                                         self.station.station_addr,
                                         now.strftime("%H:%M:%S"),
                                         len(alert_frame))

                self.station.advance(int(self.interval / 60) or 1)
            except Exception:
                logger.exception("[%s] 上报异常", self.station.station_addr)
            self._stop.wait(self.interval)


class SimulatorEngine:
    """模拟器引擎。"""

    def __init__(self, sender: Sender):
        self.sender = sender
        self.runners: list[StationRunner] = []

    def add_station(
        self,
        station: BaseStation,
        center_addr: int = 1,
        password: int = 0,
        station_type: int = 0,
        interval: float = 300.0,
        function_code: int = 0x32,
        enable_alert: bool = False,
        alert_threshold: float = 0.05,
    ) -> None:
        encoder = SL651Encoder(
            center_addr=center_addr,
            station_addr=station.station_addr_hex,
            password=password,
            station_type=station_type or station.STATION_TYPE,
        )
        runner = StationRunner(
            station, encoder, self.sender, interval, function_code,
            enable_alert=enable_alert, alert_threshold=alert_threshold,
        )
        self.runners.append(runner)
        logger.info("已添加 %s 站点 %s", station.name, station.station_addr)

    def start(self) -> None:
        for runner in self.runners:
            runner.start()
        logger.info("模拟器已启动，共 %d 个站点，按 Ctrl+C 停止", len(self.runners))
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号...")
            self.stop()

    def stop(self) -> None:
        for runner in self.runners:
            runner.stop()
        self.sender.close()
