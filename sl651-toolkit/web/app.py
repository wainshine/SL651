#!/usr/bin/env python3
"""SL651 / SL427 报文 Web 解码器 —— 单文件 Flask 应用（遥测监控台风格）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request

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
<title>SL651 / SL427 报文解码台</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 46'%3E%3Crect width='46' height='46' rx='6' fill='%230d9488'/%3E%3Cpath d='M7 20 Q13 13 19 20 T31 20 T43 20' stroke='white' stroke-width='2.5' fill='none' stroke-linecap='round'/%3E%3Cpath d='M7 29 Q13 22 19 29 T31 29 T43 29' stroke='white' stroke-width='2' fill='none' stroke-linecap='round' opacity='.6'/%3E%3C/svg%3E">
<style>
  :root {
    --bg: #f2f5f4;
    --bg-panel: #ffffff;
    --bg-inset: #f7faf9;
    --line: #dbe4e2;
    --line-soft: #e8efed;
    --text: #1d2b33;
    --text-dim: #54696f;
    --text-faint: #8aa0a8;
    --accent: #0d9488;
    --accent-dim: #ccfbf1;
    --cyan: #0e7490;
    --ok: #059669;
    --ok-bg: #ecfdf5;
    --bad: #dc2626;
    --bad-bg: #fef2f2;
    --warn: #d97706;
    --serif: "Songti SC", "STSong", "Noto Serif SC", "SimSun", serif;
    --sans: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    --mono: "SF Mono", "Menlo", "Consolas", "Courier New", monospace;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(13, 148, 136, .07), transparent),
      linear-gradient(rgba(13, 148, 136, .05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(13, 148, 136, .05) 1px, transparent 1px);
    background-size: 100% 100%, 32px 32px, 32px 32px;
  }

  .shell { max-width: 1180px; margin: 0 auto; padding: 40px 28px 64px; }

  /* ---------- 页眉 ---------- */
  header { display: flex; align-items: flex-end; justify-content: space-between;
           flex-wrap: wrap; gap: 16px; margin-bottom: 32px; }
  .brand { display: flex; align-items: center; gap: 16px; }
  .brand-mark { width: 46px; height: 46px; flex: none; }
  .brand h1 { font-family: var(--serif); font-size: 26px; font-weight: 700;
              letter-spacing: .14em; color: #14231f; }
  .brand .sub { margin-top: 5px; font-size: 11.5px; letter-spacing: .28em;
                color: var(--text-faint); text-transform: uppercase; }
  .meta-note { font-family: var(--mono); font-size: 11.5px; color: var(--text-faint);
               letter-spacing: .1em; padding-bottom: 4px; }
  .meta-note b { color: var(--accent); font-weight: 600; }

  /* ---------- 面板 ---------- */
  .panel { background: var(--bg-panel); border: 1px solid var(--line);
           border-radius: 6px; position: relative;
           box-shadow: 0 1px 3px rgba(29, 43, 51, .06), 0 4px 16px rgba(29, 43, 51, .04); }
  .panel::before { content: ""; position: absolute; top: 0; left: 12px; right: 12px;
                   height: 1px; background: linear-gradient(90deg, transparent,
                   rgba(13, 148, 136, .45), transparent); }
  .panel-head { display: flex; align-items: center; gap: 10px;
                padding: 13px 20px; border-bottom: 1px solid var(--line-soft); }
  .panel-head .dot { width: 7px; height: 7px; border-radius: 50%;
                     background: var(--accent); box-shadow: 0 0 6px rgba(13, 148, 136, .5); }
  .panel-head h2 { font-size: 12px; font-weight: 600; letter-spacing: .3em;
                   color: var(--text-dim); text-transform: uppercase; }
  .panel-body { padding: 20px; }

  /* ---------- 输入区 ---------- */
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 4px;
         overflow: hidden; background: var(--bg-panel); }
  .seg button { font-family: var(--mono); font-size: 12px; padding: 7px 18px;
                background: transparent; color: var(--text-dim); border: none;
                cursor: pointer; letter-spacing: .08em; transition: all .18s; }
  .seg button + button { border-left: 1px solid var(--line); }
  .seg button.on { background: var(--accent-dim); color: var(--accent); font-weight: 600; }
  .seg button:hover:not(.on) { color: var(--text); background: var(--bg-inset); }

  .input-row { display: flex; align-items: center; justify-content: space-between;
               gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
  .samples { display: flex; gap: 16px; align-items: center; }
  .samples .lbl { font-size: 11px; color: var(--text-faint); letter-spacing: .15em; }

  .sample-link { font-size: 12.5px; background: none; border: none; padding: 2px 0;
                 color: var(--accent); cursor: pointer; font-family: var(--sans);
                 letter-spacing: .03em; transition: color .15s; }
  .sample-link::before { content: "› "; font-weight: 600; }
  .sample-link:hover { color: #0f766e; text-decoration: underline;
                       text-underline-offset: 3px; }

  .ghost-btn { font-size: 12px; padding: 6px 14px; border-radius: 4px;
               border: 1px solid var(--line); background: var(--bg-panel);
               color: var(--text-dim); cursor: pointer; transition: all .18s;
               font-family: var(--sans); letter-spacing: .05em; }
  .ghost-btn:hover { border-color: var(--accent); color: var(--accent); }

  .hex-wrap { position: relative; border: 1px solid var(--line); border-radius: 4px;
              background: var(--bg-inset); transition: border-color .2s, box-shadow .2s; }
  .hex-wrap:focus-within { border-color: var(--accent);
                           box-shadow: 0 0 0 3px rgba(13, 148, 136, .12); }
  textarea { width: 100%; height: 150px; background: transparent; border: none;
             outline: none; resize: vertical; padding: 14px 16px;
             font-family: var(--mono); font-size: 13px; line-height: 1.9;
             color: var(--cyan); letter-spacing: .06em; caret-color: var(--accent); }
  textarea::placeholder { color: var(--text-faint); }
  .hex-count { position: absolute; right: 12px; bottom: 8px; font-family: var(--mono);
               font-size: 11px; color: var(--text-faint); pointer-events: none; }
  .hex-count b { color: var(--accent); font-weight: 500; }

  .action-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
  .run-btn { position: relative; font-size: 13px; font-weight: 600; letter-spacing: .2em;
             padding: 10px 34px; border: 1px solid var(--accent); border-radius: 4px;
             background: var(--accent); color: #ffffff;
             cursor: pointer; transition: all .2s; overflow: hidden; }
  .run-btn:hover { background: #0f766e; border-color: #0f766e;
                   box-shadow: 0 4px 14px rgba(13, 148, 136, .35); }
  .run-btn:disabled { opacity: .55; cursor: wait; }
  .hint { font-size: 11px; color: var(--text-faint); margin-left: auto;
          font-family: var(--mono); letter-spacing: .04em; }
  kbd { font-family: var(--mono); font-size: 10px; border: 1px solid var(--line);
        border-bottom-width: 2px; border-radius: 3px; padding: 1px 5px;
        color: var(--text-dim); background: var(--bg-panel); }

  /* ---------- 错误 ---------- */
  .err { display: none; margin-top: 16px; border: 1px solid #fca5a5;
         background: var(--bad-bg); border-radius: 4px; padding: 12px 16px;
         font-size: 13px; color: var(--bad); font-family: var(--mono); }
  .err.show { display: block; animation: rise .3s ease both; }
  .err .tag { font-family: var(--sans); font-weight: 600; margin-right: 8px;
              letter-spacing: .1em; }

  /* ---------- 结果区 ---------- */
  #results { margin-top: 22px; display: none; }
  #results.show { display: block; }

  .r-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
  .r-item { display: flex; gap: 12px; padding: 9px 20px;
            border-bottom: 1px solid var(--line-soft); font-size: 13px; }
  .r-item:nth-child(odd) { border-right: 1px solid var(--line-soft); }
  .r-item .k { flex: none; width: 110px; color: var(--text-faint);
               font-size: 12px; padding-top: 1px; letter-spacing: .08em; }
  .r-item .v { font-family: var(--mono); color: var(--text); word-break: break-all; }

  .crc-pill { margin-left: auto; font-size: 11.5px; font-weight: 600;
              letter-spacing: .12em; padding: 4px 14px; border-radius: 20px; }
  .crc-pill.ok { color: var(--ok); background: var(--ok-bg);
                 border: 1px solid #a7f3d0; }
  .crc-pill.bad { color: var(--bad); background: var(--bad-bg);
                  border: 1px solid #fca5a5; }
  .el-count { margin-left: auto; font-size: 11.5px; color: var(--text-faint);
              letter-spacing: .08em; font-family: var(--mono); }
  .el-count b { color: var(--text-dim); font-weight: 600; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  thead th { font-size: 11px; font-weight: 600; letter-spacing: .22em;
             color: var(--text-faint); text-align: left; padding: 10px 16px;
             border-bottom: 1px solid var(--line); text-transform: uppercase; }
  tbody td { padding: 9px 16px; border-bottom: 1px solid var(--line-soft); }
  tbody tr { transition: background .15s; }
  tbody tr:hover { background: #f0fdfa; }
  td.code { font-family: var(--mono); color: var(--accent); font-weight: 600; }
  td.val { font-family: var(--mono); color: #14231f; font-weight: 500; }
  td.raw { font-family: var(--mono); font-size: 12px; color: var(--text-dim);
           letter-spacing: .05em; }
  .empty { padding: 22px 16px; text-align: center; color: var(--text-faint);
           font-size: 12.5px; letter-spacing: .1em; }

  .stack > .panel { margin-bottom: 18px; }

  @keyframes rise { from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: none; } }
  .anim > * { animation: rise .45s cubic-bezier(.2, .8, .3, 1) both; }
  .anim > *:nth-child(1) { animation-delay: .02s; }
  .anim > *:nth-child(2) { animation-delay: .1s; }

  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
  .panel-head .dot { animation: blink 2.4s ease-in-out infinite; }

  footer { margin-top: 44px; padding-top: 18px; border-top: 1px solid var(--line-soft);
           display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
           font-size: 11px; color: var(--text-faint); letter-spacing: .12em; }

  @media (max-width: 720px) {
    .shell { padding: 24px 14px 48px; }
    .r-grid { grid-template-columns: 1fr; }
    .r-item:nth-child(odd) { border-right: none; }
  }
</style>
</head>
<body>
<div class="shell">

  <header>
    <div class="brand">
      <svg class="brand-mark" viewBox="0 0 46 46" fill="none" aria-hidden="true">
        <rect x="1" y="1" width="44" height="44" rx="6" stroke="#c3d4d0" stroke-width="1.5"/>
        <path d="M7 20 Q13 13 19 20 T31 20 T43 20" stroke="#0d9488" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M7 28 Q13 21 19 28 T31 28 T43 28" stroke="#0e7490" stroke-width="1.5" fill="none" stroke-linecap="round" opacity=".55"/>
        <path d="M7 35 Q13 30 19 35 T31 35 T43 35" stroke="#0d9488" stroke-width="1" fill="none" stroke-linecap="round" opacity=".3"/>
      </svg>
      <div>
        <h1>报文解码台</h1>
        <div class="sub">HYDROLOGIC TELEMETRY FRAME DECODER</div>
      </div>
    </div>
    <div class="meta-note"><b>SL651</b>-2014&nbsp;·&nbsp;<b>SL/T 427</b>-2021&nbsp;·&nbsp;__VERSION__</div>
  </header>

  <div class="panel">
    <div class="panel-head">
      <span class="dot"></span><h2>原始报文</h2>
      <div class="seg" style="margin-left:auto">
        <button id="seg-sl651" class="on" type="button">SL651</button>
        <button id="seg-sl427" type="button">SL427</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="input-row">
        <div class="samples">
          <span class="lbl">载入示例</span>
          <button class="sample-link" type="button" onclick="loadSample('sl651')">SL651 定时报</button>
          <button class="sample-link" type="button" onclick="loadSample('sl427')">SL427 自报帧</button>
        </div>
        <button class="ghost-btn" type="button" onclick="clearAll()">清空</button>
      </div>
      <div class="hex-wrap">
        <textarea id="hex" spellcheck="false"
          placeholder="粘贴十六进制报文，支持空格 / 换行分隔；以 68 开头自动识别为 SL427，其余按 SL651 解析"></textarea>
        <div class="hex-count" id="hexCount">0 bytes</div>
      </div>
      <div class="action-row">
        <button class="run-btn" id="runBtn" type="button" onclick="runDecode()">解 析</button>
        <span class="hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> 快捷解析</span>
      </div>
      <div class="err" id="errBox"><span class="tag">解码失败</span><span id="errMsg"></span></div>
    </div>
  </div>

  <div id="results">
    <div class="stack anim">
      <div class="panel">
        <div class="panel-head">
          <span class="dot"></span><h2>帧信息</h2>
          <span class="crc-pill" id="crcPill"></span>
        </div>
        <div class="r-grid" id="frameInfo"></div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <span class="dot"></span><h2>要素列表</h2>
          <span class="el-count" id="elCount"></span>
        </div>
        <div id="elTable"></div>
      </div>
    </div>
  </div>

  <footer>
    <span>SL651-TOOLKIT · DECODER CONSOLE</span>
    <span>CRC-16/MODBUS · CRC-8/0xE5</span>
  </footer>
</div>

<script>
var SAMPLES = { sl651: __SL651__, sl427: __SL427__ };
var proto = "sl651";
var busy = false;

var hexEl = document.getElementById("hex");

function setProto(p) {
  proto = p;
  document.getElementById("seg-sl651").classList.toggle("on", p === "sl651");
  document.getElementById("seg-sl427").classList.toggle("on", p === "sl427");
}
document.getElementById("seg-sl651").onclick = function () { setProto("sl651"); };
document.getElementById("seg-sl427").onclick = function () { setProto("sl427"); };

function cleanHex(s) { return (s || "").replace(/[^0-9a-fA-F]/g, ""); }

function updateCount() {
  var n = Math.floor(cleanHex(hexEl.value).length / 2);
  document.getElementById("hexCount").innerHTML = "<b>" + n + "</b> bytes";
}

hexEl.addEventListener("input", function () {
  updateCount();
  var h = cleanHex(hexEl.value).toUpperCase();
  if (h.startsWith("68") && proto !== "sl427") setProto("sl427");
  else if ((h.startsWith("7E7E") || h.startsWith("01")) && proto !== "sl651") setProto("sl651");
});

function loadSample(p) {
  setProto(p);
  hexEl.value = SAMPLES[p] || "";
  updateCount();
  runDecode();
}
function clearAll() {
  hexEl.value = "";
  updateCount();
  document.getElementById("results").classList.remove("show");
  document.getElementById("errBox").classList.remove("show");
}

document.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runDecode(); }
});

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function showError(msg) {
  document.getElementById("errMsg").textContent = msg;
  document.getElementById("errBox").classList.add("show");
  document.getElementById("results").classList.remove("show");
}

function renderResult(data) {
  document.getElementById("errBox").classList.remove("show");

  var pill = document.getElementById("crcPill");
  if (data.crc_ok === true)  { pill.className = "crc-pill ok";  pill.textContent = "CRC 校验通过"; }
  else if (data.crc_ok === false) { pill.className = "crc-pill bad"; pill.textContent = "CRC 校验失败"; }
  else { pill.className = "crc-pill"; pill.textContent = ""; pill.style.display = "none"; }
  if (data.crc_ok === true || data.crc_ok === false) pill.style.display = "";

  var infoHtml = "";
  data.info.forEach(function (kv) {
    infoHtml += '<div class="r-item"><span class="k">' + esc(kv[0]) +
                '</span><span class="v">' + esc(kv[1]) + "</span></div>";
  });
  document.getElementById("frameInfo").innerHTML = infoHtml;

  var els = data.elements || [];
  document.getElementById("elCount").innerHTML = "共 <b>" + els.length + "</b> 项";
  var box = document.getElementById("elTable");
  if (!els.length) {
    box.innerHTML = '<div class="empty">— 无要素数据 —</div>';
  } else {
    var hasCode = els[0].code !== undefined;
    var h = "<table><thead><tr>" +
            (hasCode ? "<th>编码</th>" : "") +
            "<th>名称</th><th>值</th>" +
            (hasCode ? "" : "<th>单位</th>") +
            "<th>原始 HEX</th></tr></thead><tbody>";
    els.forEach(function (el) {
      h += "<tr>" +
           (hasCode ? '<td class="code">' + esc(el.code) + "</td>" : "") +
           "<td>" + esc(el.name) + "</td>" +
           '<td class="val">' + esc(el.value) + "</td>" +
           (hasCode ? "" : "<td>" + esc(el.unit) + "</td>") +
           '<td class="raw">' + esc(el.raw) + "</td></tr>";
    });
    box.innerHTML = h + "</tbody></table>";
  }

  var r = document.getElementById("results");
  r.classList.remove("show");
  void r.offsetWidth;
  r.classList.add("show");
}

function runDecode() {
  var hex = cleanHex(hexEl.value);
  if (!hex || busy) return;
  if (hex.length % 2 !== 0) { showError("HEX 长度为奇数，请检查报文是否完整"); return; }

  busy = true;
  var btn = document.getElementById("runBtn");
  btn.disabled = true;
  btn.textContent = "解析中…";

  fetch("/api/decode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proto: proto, hex: hex })
  })
    .then(function (res) { return res.json().then(function (j) { return { ok: res.ok, j: j }; }); })
    .then(function (r) {
      if (!r.ok) showError(r.j.error || "未知错误");
      else renderResult(r.j);
    })
    .catch(function (e) { showError("请求失败：" + e.message); })
    .finally(function () {
      busy = false;
      btn.disabled = false;
      btn.textContent = "解 析";
    });
}

updateCount();
</script>
</body>
</html>
"""

from sl651 import __version__ as TOOLKIT_VERSION

HTML = (
    HTML
    .replace("__SL651__", json.dumps(SL651_SAMPLE))
    .replace("__SL427__", json.dumps(SL427_SAMPLE))
    .replace("__VERSION__", f"v{TOOLKIT_VERSION}")
)


def frame_info(result: dict) -> dict:
    info = {}
    if "center_addr" in result:
        info["中心站址"] = result.get("center_addr", "")
    if "station_addr" in result:
        info["遥测站址"] = result.get("station_addr", "")
    if "addr" in result:
        info["地址"] = result.get("addr", "")
    if "password" in result:
        info["密码"] = "****"
    if "function_code" in result:
        func_name = result.get("function_name") or ""
        info["功能码"] = f"{result['function_code']} ({func_name})" if func_name else result["function_code"]
    if "afn" in result:
        afn_name = result.get("afn_name") or ""
        info["AFN"] = f"{result['afn']} ({afn_name})" if afn_name else result["afn"]
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
    if "data_len" in result:
        info["用户数据长度"] = f"{result['data_len']} 字节"
    if "crc_ok" in result:
        crc_pair = ""
        if "crc_received" in result:
            crc_pair = f"{result['crc_received']} / {result['crc_calculated']}"
        elif "crc_recv" in result:
            crc_pair = f"{result['crc_recv']} / {result['crc_calc']}"
        if crc_pair:
            info["CRC（接收/计算）"] = crc_pair
    warns = result.get("warnings") or []
    if warns:
        info["告警"] = "；".join(str(w) for w in warns)
    return info


def do_decode(proto: str, hex_str: str) -> dict:
    if proto == "sl651":
        from sl651 import SL651Decoder
        r = SL651Decoder().decode_hex(hex_str)
    else:
        from sl427 import SL427Decoder
        r = SL427Decoder().decode_hex(hex_str)
    return r.to_dict()


@app.route("/", methods=["GET"])
def index():
    return HTML


@app.route("/api/decode", methods=["POST"])
def api_decode():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "请求体须为 JSON 对象"}), 400
    proto = payload.get("proto", "sl651")
    hex_raw = payload.get("hex")
    if proto not in ("sl651", "sl427"):
        return jsonify({"error": f"不支持的协议: {proto}"}), 400
    if not isinstance(hex_raw, str) or not hex_raw.strip():
        return jsonify({"error": "报文为空或不是字符串"}), 400
    hex_str = hex_raw.strip()
    try:
        result = do_decode(proto, hex_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({
        "info": list(frame_info(result).items()),
        "elements": result.get("elements", []),
        "crc_ok": result.get("crc_ok"),
    })


def main():
    print("SL651/SL427 报文解码台 Web UI")
    print("浏览器访问: http://localhost:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
