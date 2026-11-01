"""SL651 / SL427 共享异常类型。

历史上 `sl651.encoder`、`sl427.encoder` 各自定义 `EncodeError`，
`sl651.decoder`、`sl427.decoder` 各自定义 `DecodeError`，导致跨包
`except EncodeError` 无法捕获另一个协议的异常。本模块把它们收敛为
同一组类，并在各子模块保留同名别名以兼容旧导入路径。
"""

from __future__ import annotations


class ProtocolError(Exception):
    """协议编解码错误的公共基类。"""


class EncodeError(ProtocolError):
    """编码异常。"""


class DecodeError(ProtocolError):
    """解码异常。"""
