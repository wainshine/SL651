# SL651 水文规约工具包

基于《水文监测数据通信规约 SL651-2014》和《水资源监测数据传输规约 SL/T 427-2021》实现的 Python 编解码工具包，含设备模拟器。

## 目录

```
SL651/
├── sl651-toolkit/          # Python 工具包（核心代码）
│   ├── sl651/              # SL651 协议编解码
│   ├── sl427/              # SL427 协议编解码
│   ├── simulator/          # 设备模拟器
│   ├── tools/              # CLI 工具
│   ├── web/                # Web 解码界面
│   ├── docs/               # 需求文档 + 交接文档
│   ├── tests/              # 41 项自测（+10 项盲区测试）
│   └── README.md           # 工具包详细文档
├── 行业规范/               # PDF 规范文件（gitignore，不入库）
└── .gitignore
```

## 快速开始

```bash
cd sl651-toolkit
pip install -r requirements.txt

# 解码一条报文
python tools/decode_cli.py sl651 --hex "7E7E..."

# 跑全部测试（41 项）
python tests/test_sl651.py
```

## 详细文档

- **项目规格**：`sl651-toolkit/docs/project.md`
- **交接文档**：`sl651-toolkit/docs/handoff_main.md`
- **工具包 README**：`sl651-toolkit/README.md`
- **各模块 README**：`sl651/README.md`、`sl427/README.md`、`simulator/README.md`、`tools/README.md`、`web/README.md`

## 行业规范

规范 PDF 文件在 `行业规范/` 目录下（`.gitignore` 排除，不入库），包含：
- 水文监测数据通信规约 SL651-2014
- 水资源监测数据传输规约 SL427-2021
- 福建省水文监测数据接入规定 V1.0
- 水利技术标准体系表（2024版）等

## 致谢

本项目在 SL651/SL427 协议解析思路上部分参考了 [南京蓉水自动化技术研究所](http://njnrs.com) 的在线报文解析工具。

## 许可证

[Apache-2.0](LICENSE)
