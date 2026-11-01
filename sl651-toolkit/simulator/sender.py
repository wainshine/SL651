"""SL651 报文发送器。

支持两种发送模式：
- MqttxSender: 通过 mqttx CLI 子进程发布 MQTT 消息
- TcpSender: 通过 TCP socket 发送原始 SL651 帧
"""

from __future__ import annotations

import logging
import socket
import subprocess
import threading
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SendError(Exception):
    """发送异常。"""


class Sender(ABC):
    """发送器抽象基类。"""

    @abstractmethod
    def send(self, hex_msg: str, station_addr: str) -> bool:
        """发送一条报文。返回是否成功。"""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接（如需）。"""
        ...


class MqttxSender(Sender):
    """通过 mqttx CLI 发送 MQTT 消息。

    使用前需安装 mqttx CLI（独立二进制，参考 README 环境要求）
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_template: str = "sl651/{station_addr}/uplink",
        timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.topic_template = topic_template
        self.timeout = timeout
        if password:
            logger.warning(
                "MQTT 密码将通过 mqttx 命令行参数传递，可能出现在进程列表；"
                "建议使用专用低权限账号或受限 broker"
            )

    def send(self, hex_msg: str, station_addr: str = "") -> bool:
        topic = self.topic_template.format(station_addr=station_addr)
        cmd = [
            "mqttx", "pub",
            "-t", topic,
            "-h", self.host,
            "-p", str(self.port),
            "-m", hex_msg,
            "-q", "0",
        ]
        if self.username:
            cmd.extend(["-u", self.username, "-P", self.password])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                logger.warning("mqttx pub 失败 (rc=%d): %s", result.returncode, result.stderr.strip())
                return False
            return True
        except FileNotFoundError:
            raise SendError(
                "未找到 mqttx 命令。请参考 README 环境要求安装 mqttx CLI\n"
                "或下载: https://mqttx.app/downloads"
            )
        except subprocess.TimeoutExpired:
            logger.warning("mqttx pub 超时 (%ds)", self.timeout)
            return False
        except Exception as e:
            logger.warning("mqttx pub 异常: %s", e)
            return False

    def close(self) -> None:
        pass


class TcpSender(Sender):
    """通过 TCP socket 发送原始 SL651 帧。

    多站点共享同一实例时是线程安全的（内部持锁串行化发送）。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5001,
        timeout: int = 10,
        reconnect: bool = False,
        reconnect_delay: float = 1.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay
        self._sock: socket.socket | None = None
        self._connected = False
        self._lock = threading.Lock()

    def _ensure_connected(self) -> None:
        if self._connected and self._sock is not None:
            return
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            self._connected = True
        except OSError as e:
            self._close_sock()
            logger.warning("TCP 连接 %s:%d 失败: %s", self.host, self.port, e)

    def _close_sock(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._connected = False

    def send(self, hex_msg: str, station_addr: str = "") -> bool:
        # 重连等待不能持有 self._lock：否则多站点共享时链路故障期所有站点串行阻塞。
        if not self._connected and self.reconnect:
            time.sleep(max(0.0, float(self.reconnect_delay)))
        with self._lock:
            try:
                self._ensure_connected()
                if self._sock is None:
                    return False
                frame = bytes.fromhex(hex_msg)
                self._sock.sendall(frame)
                return True
            except (socket.timeout, ConnectionError, OSError, ValueError) as e:
                logger.warning("TCP 发送失败: %s", e)
                self._close_sock()
                return False

    def close(self) -> None:
        with self._lock:
            self._close_sock()
