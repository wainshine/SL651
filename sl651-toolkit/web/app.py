#!/usr/bin/env python3
"""SL651 / SL427 报文 Web 解码器 —— 单文件 Flask 应用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, render_template_string

app = Flask(__name__)

SL651_SAMPLE = (
    "7E7E2500418D23370000320030020C06230601010314"
    "F1F100418D23374BF0F02306010100"
    "20190000003B2300037865221900000026190000003812128503"
    "5AC6"
)

SL427_SAMPLE = "681568B40102030405C05545040020700030151412052600AD16"

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>报文解码器</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f0f2f5; color: #1a1a2e; padding: 24px 16px; }
  .container { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 22px; margin-bottom: 20px; color: #0f1a2e; }
  h2 { font-size: 16px; margin: 18px 0 10px; color: #2c3e50; }

  .card { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
          padding: 20px 24px; margin-bottom: 16px; }

  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .toolbar label { font-weight: 600; font-size: 14px; }
  select { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }

  textarea { width: 100%; height: 140px; font-family: "SF Mono", "Menlo", "Consolas", monospace;
             font-size: 13px; padding: 10px; border: 1px solid #ccc; border-radius: 6px;
             resize: vertical; background: #fafafa; }
  textarea:focus { border-color: #5b8def; outline: none; box-shadow: 0 0 0 2px rgba(91,141,239,.2); }

  .actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  button { padding: 8px 18px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px;
           background: #fff; cursor: pointer; font-weight: 500; transition: .15s; }
  button:hover { background: #f5f5f5; }
  button.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
  button.primary:hover { background: #1d4ed8; }

  .error { background: #fef2f2; color: #b91c1c; border: 1px solid #fca5a5;
           border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
  th { background: #f8fafc; font-weight: 600; color: #475569; white-space: nowrap; }
  tr:hover td { background: #f1f5f9; }

  .kv td:first-child { font-weight: 600; color: #374151; width: 140px; }
  .crc-ok { color: #16a34a; font-weight: 600; }
  .crc-fail { color: #dc2626; font-weight: 600; }

  .sample-btn { font-size: 12px; padding: 5px 12px; }
  .empty { color: #9ca3af; font-style: italic; padding: 12px; }
</style>
</head>
<body>
<div class="container">

<h1>SL651 / SL427 报文解码器</h1>

<form method="POST" action="/" class="card">
  <div class="toolbar">
    <label for="proto">协议:</label>
    <select name="proto" id="proto">
      <option value="sl651" {% if proto == 'sl651' %}selected{% endif %}>SL651</option>
      <option value="sl427" {% if proto == 'sl427' %}selected{% endif %}>SL427</option>
    </select>
    <button type="button" class="sample-btn" onclick="loadSample('sl651')">SL651 示例</button>
    <button type="button" class="sample-btn" onclick="loadSample('sl427')">SL427 示例</button>
  </div>

  <textarea name="hex" id="hex" placeholder="在此粘贴十六进制报文...">{{ hex_str }}</textarea>

  <div class="actions">
    <button type="submit" class="primary">解析</button>
    <button type="button" onclick="clearForm()">清空</button>
  </div>
</form>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

{% if result %}

<div class="card">
  <h2>帧信息</h2>
  <table class="kv">
    <tbody>
    {% for key, val in frame_info(result).items() %}
    <tr>
      <td>{{ key }}</td>
      <td>
        {% if key == 'CRC 校验' %}
          {% if val == '通过' %}
            <span class="crc-ok">{{ val }}</span>
          {% else %}
            <span class="crc-fail">{{ val }}</span>
          {% endif %}
        {% else %}
          {{ val }}
        {% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<div class="card">
  <h2>要素列表</h2>
  {% if result.elements %}
  {% set has_code = 'code' in result.elements.0 if result.elements else false %}
  <table>
    <thead>
    <tr>
      {% if has_code %}<th>编码</th>{% endif %}
      <th>名称</th>
      <th>值</th>
      {% if not has_code %}<th>单位</th>{% endif %}
      <th>原始 HEX</th>
    </tr>
    </thead>
    <tbody>
    {% for el in result.elements %}
    <tr>
      {% if has_code %}<td>{{ el.code }}</td>{% endif %}
      <td>{{ el.name }}</td>
      <td>{{ el.value }}</td>
      {% if not has_code %}<td>{{ el.unit }}</td>{% endif %}
      <td><code>{{ el.raw }}</code></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">无要素数据</p>
  {% endif %}
</div>

{% endif %}

</div>

<script>
  var SAMPLES = {
    sl651: {{ sl651_sample_json|safe }},
    sl427: {{ sl427_sample_json|safe }}
  };
  function loadSample(proto) {
    document.getElementById('proto').value = proto;
    document.getElementById('hex').value = SAMPLES[proto] || '';
  }
  function clearForm() {
    document.getElementById('hex').value = '';
  }
</script>
</body>
</html>"""


def frame_info(result: dict) -> dict:
    info = {}
    if "center_addr" in result:
        info["中心站址"] = result.get("center_addr", "")
    if "station_addr" in result:
        info["遥测站址"] = result.get("station_addr", "")
    if "addr" in result:
        info["地址"] = result.get("addr", "")
    if "password" in result:
        info["密码"] = result.get("password", "")
    if "function_code" in result:
        info["功能码"] = f"{result['function_code']} ({result.get('function_name', '')})".strip()
    if "afn" in result:
        info["AFN"] = f"{result['afn']} ({result.get('afn_name', '')})".strip()
    if "ctrl_func_name" in result and result.get("ctrl_func_name"):
        info["控制功能"] = result["ctrl_func_name"]
    if "message_type" in result and result.get("message_type"):
        info["报文类型"] = result["message_type"]
    if "direction" in result:
        info["方向"] = result["direction"]
    if "body_length" in result:
        info["正文长度"] = str(result["body_length"])
    if "serial" in result:
        info["流水号"] = result["serial"]
    if "tx_time" in result:
        info["发报时间"] = result["tx_time"]
    if "station_type" in result:
        info["测站类别"] = result["station_type"]
    if "obs_time" in result:
        info["观测时间"] = result["obs_time"]
    if "encoding" in result:
        info["编码"] = result["encoding"]
    if "frame_length" in result:
        info["帧长度"] = f"{result['frame_length']} 字节"
    if "crc_ok" in result:
        if result["crc_ok"]:
            info["CRC 校验"] = "通过"
            if "crc_received" in result:
                info["CRC（接收/计算）"] = f"{result['crc_received']} / {result['crc_calculated']}"
            elif "crc_recv" in result:
                info["CRC（接收/计算）"] = f"{result['crc_recv']} / {result['crc_calc']}"
        else:
            info["CRC 校验"] = "失败"
            if "crc_received" in result:
                info["CRC（接收/计算）"] = f"{result['crc_received']} / {result['crc_calculated']}"
            elif "crc_recv" in result:
                info["CRC（接收/计算）"] = f"{result['crc_recv']} / {result['crc_calc']}"
    return info


@app.route("/", methods=["GET", "POST"])
def decode():
    result = None
    error = None
    hex_str = ""
    proto = "sl651"

    if request.method == "POST":
        hex_str = request.form.get("hex", "").strip()
        proto = request.form.get("proto", "sl651")
        if hex_str:
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

    return render_template_string(
        HTML,
        result=result,
        error=error,
        hex_str=hex_str,
        proto=proto,
        frame_info=frame_info,
        sl651_sample_json=json.dumps(SL651_SAMPLE),
        sl427_sample_json=json.dumps(SL427_SAMPLE),
    )


def main():
    print("SL651/SL427 报文解码器 Web UI")
    print("浏览器访问: http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=True)


if __name__ == "__main__":
    main()
