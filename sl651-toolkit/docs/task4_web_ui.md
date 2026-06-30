# 任务 4：Web 解码界面

## 职责边界

新建 `web/` 目录，提供一个 Flask Web 应用，在浏览器中粘贴十六进制报文、选协议、点解析、看结果。

**不需要做**：
- 不需要修改协议代码（sl651/、sl427/）
- 不需要安装额外 Python 包（用标准库 + 已有代码）
- 不需要前端框架（纯 HTML + 内联 CSS）
- 不需要持久化、不需要登录

## 背景知识

### 解码器已有 Python API

```python
from sl651 import SL651Decoder
r = SL651Decoder().decode_hex("7E7E...")
data = r.to_dict()  # 返回 dict，可直接 json.dumps

from sl427 import SL427Decoder
r = SL427Decoder().decode_hex("681568...")
data = r.to_dict()
```

`to_dict()` 返回的结构示例：

```json
{
  "center_addr": "25",
  "station_addr": "00418D2337",
  "function_code": "0x32",
  "function_name": "定时报",
  "crc_ok": true,
  "elements": [
    {"code": "39", "name": "瞬时河道水位", "value": "0.345 m", "unit": "m", "raw": "00000345"}
  ]
}
```

### Flask 最简应用

```python
from flask import Flask, request, render_template_string

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def decode():
    result = None
    error = None
    if request.method == "POST":
        hex_str = request.form.get("hex", "")
        proto = request.form.get("proto", "sl651")
        try:
            if proto == "sl651":
                from sl651 import SL651Decoder
                r = SL651Decoder().decode_hex(hex_str)
            else:
                from sl427 import SL427Decoder
                r = SL427Decoder().decode_hex(hex_str)
            result = r.to_dict()
        except Exception as e:
            error = str(e)
    return render_template_string(HTML_TEMPLATE, result=result, error=error)

app.run(host="0.0.0.0", port=8080, debug=True)
```

将 HTML 模板作为字符串内嵌在 Python 文件中（单文件部署，无需 templates 目录）。

## 要读的文件

| 文件 | 读什么 |
|------|--------|
| `sl651/decoder.py` | `SL651Decoder.decode_hex()`、`DecodedMessage.to_dict()` 返回结构 |
| `sl427/decoder.py` | `SL427Decoder.decode_hex()`、`DecodedMessage.to_dict()` 返回结构 |
| `sl651/decoder.py` | `DecodeError` 异常类 |

## 具体要做的事

### 1. 创建 `web/app.py`

单文件 Flask 应用，包含以下路由：

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET/POST | 主解码页面 |

### 2. HTML 模板（内嵌在 app.py 中）

模板结构：

```
┌─────────────────────────────────────────┐
│  SL651 / SL427 报文解码器                │
├─────────────────────────────────────────┤
│  协议: [sl651 ▼] [sl427]                │
│  ┌──────────────────────────────────┐   │
│  │ 文本框（粘贴 hex）                 │   │
│  │                                  │   │
│  └──────────────────────────────────┘   │
│  [解析] [清空] [加载示例]                │
├─────────────────────────────────────────┤
│  错误信息（红色）                        │
├─────────────────────────────────────────┤
│  帧信息表                                │
│  ┌──────────┬──────────┐               │
│  │ 中心站址  │    25    │               │
│  │ 功能码    │ 0x32    │               │
│  │ CRC校验   │  通过   │               │
│  └──────────┴──────────┘               │
│                                         │
│  要素列表                                │
│  ┌────┬──────────┬───────┬──────┐     │
│  │ 编码│   名称   │  值   │ 单位 │     │
│  ├────┼──────────┼───────┼──────┤     │
│  │ 39 │瞬时水位  │ 0.345 │  m   │     │
│  └────┴──────────┴───────┴──────┘     │
└─────────────────────────────────────────┘
```

要素表根据协议不同展示不同列：
- SL651: 编码 / 名称 / 值 / 单位 / 原始HEX
- SL427: 名称 / 值 / 单位 / 原始HEX

### 3. 示例数据

提供两个示例按钮：
- SL651 示例：njnrs 水库站定时报 `7E7E25...`
- SL427 示例：流速自报 `681568B4...`

### 4. 错误处理

解析失败时在页面上方显示错误信息即可，不跳转、不弹框。对应 `DecodeError` 和其他 `Exception`。

## 验收标准

```bash
cd sl651-toolkit
python web/app.py
# 浏览器打开 http://localhost:8080
```

操作流程：
1. 选择协议 "SL651"
2. 粘贴 `7E7E2500418D23370000320030020C06230601010314F1F100418D23374BF0F0230601010020190000003B23000378652219000000261900000038121285035AC6`
3. 点"解析"
4. 看到帧信息表（中心站址=25, 功能码=0x32 定时报, CRC=通过）+ 5 行要素
5. 切到 SL427 → 粘贴 `681568...` → 解析 → 看到流速值和告警状态即可视为通过
