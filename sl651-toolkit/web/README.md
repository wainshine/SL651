# web — Web 解码界面

## 概述

单文件 Flask 应用，在浏览器中粘贴十六进制报文 → 选协议 → 解析展示。

## 文件清单

| 文件 | 说明 |
|------|------|
| `app.py` | Flask 应用（含内嵌 HTML 模板），单文件部署 |

## 启动

```bash
cd sl651-toolkit
python web/app.py
# 浏览器打开 http://localhost:5050
```

## 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面（亮色遥测监控台风格，无刷新解析） |
| `/api/decode` | POST | JSON 解码接口：`{"proto": "sl651\|sl427", "hex": "..."}` → `{"info": [[k,v]...], "elements": [...], "crc_ok": bool}` |

## 功能

- 支持 SL651 / SL427 双协议（分段切换 + 按帧首字节自动识别：`68`→SL427，`7E7E`/`01`→SL651）
- SL651：支持 `7E7E` (HEX/BCD) 和 `0101` (ASCII) 两种帧起始
- "加载示例" 按钮：njnrs 水库站定时报、SL427 流速自报
- CRC 校验徽标（通过=绿色，失败=红色）
- 要素表格（SL651 含编码列，SL427 含单位列）
- 字节计数、错误提示栏、`Ctrl+Enter` 快捷解析

## 依赖

- `sl651/` — SL651Decoder
- `sl427/` — SL427Decoder
- `flask` — 已含于 `requirements.txt`
