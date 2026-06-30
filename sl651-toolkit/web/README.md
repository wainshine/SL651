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
| `/` | GET/POST | 主页面：协议选择、hex 输入、解析结果展示 |

## 功能

- 支持 SL651 / SL427 双协议
- SL651：支持 `7E7E` (HEX/BCD) 和 `0101` (ASCII) 两种帧起始
- "加载示例" 按钮：njnrs 水库站定时报、SL427 流速自报
- CRC 校验着色（通过=绿色，失败=红色）
- 要素表格（SL651 含编码列，SL427 含单位列）
- 错误提示（红色提示栏）

## 依赖

- `sl651/` — SL651Decoder
- `sl427/` — SL427Decoder
- `flask` — 需要单独安装：`pip install flask`
