# A股投资分析 Agent

一个基于 DeepSeek + LangChain 的个人A股投资助手，支持实时行情、技术分析、新闻汇总、风险监控、仓位管理、收益追踪、板块轮动、策略回测和AI选股。

## 功能

- 🔍 **实时行情查询** - 个股行情、大盘概况、热门股票
- 📊 **技术分析** - MA均线、MACD、RSI 等技术指标
- 📰 **新闻资讯** - 财经新闻、个股新闻、板块资金流向
- 📈 **基本面分析** - 市盈率、市净率、营收增速等
- ⚠️ **风险监控** - 止损止盈预警、异动提醒
- 📝 **知识管理** - 存储和检索投资笔记、研报
- 📅 **定时任务** - 每日日报、盘前概览、定时风控检查
- 📱 **消息推送** - Server酱/企业微信通知到手机
- 💰 **仓位管理** - 网格交易计算、加仓分析、定投模拟
- 📉 **收益追踪** - 每日持仓快照、收益曲线、周/月/年统计
- 🔄 **板块轮动** - 板块强弱排名、轮动信号、板块对比
- 🧪 **策略回测** - 均线策略、网格策略、定投策略回测
- 🎯 **AI选股估值** - PE/PB分位数分析、低估值筛选、AI综合分析

## 快速开始

### 1. 安装依赖

**macOS**

先在终端运行 `python3.12 --version`。如果提示 `command not found`，请先安装 Python 3.12，或把已有的 Python 3.12 加入 `PATH`，也可以用其绝对路径创建虚拟环境。[Python 在 macOS 上的安装说明](https://docs.python.org/zh-cn/3.12/using/mac.html)

```bash
cd investment-agent
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows**

```bash
cd investment-agent
pip install -r requirements.txt
```

### 2. 配置 API Key

从本机打开看板，在右上角点击 **DeepSeek 接入**，填入从 DeepSeek 平台创建的 API Key，再点击 **验证并保存**。成功后密钥会写入项目的 `.env`，当前看板即可用于 AI 判级。

也可以在启动前手动配置。

复制示例配置后填写自己的密钥（`.env` 已被 Git 忽略）：

```bash
# macOS
cp .env.example .env
```

```bat
:: Windows（命令提示符）
copy .env.example .env
```

```env
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
```

DeepSeek 注册地址: https://platform.deepseek.com/

### 3. 运行

**桌面版**：macOS 在 Finder 双击 `start.command`，也可以在终端运行 `./start.command`。如果脚本缺少执行权限，先运行 `chmod +x start.command`。关闭桌面窗口即可退出。Windows 双击 `start.vbs`，也可以运行 `start.bat`。

**Web 版和命令行**：macOS 在新终端先运行 `source .venv/bin/activate`。

```bash
# Web 界面
python main.py --web

# 交互模式（命令行对话）
python main.py

# 立即生成日报
python main.py --report

# 检查持仓风险
python main.py --monitor

# 启动定时任务（后台运行）
python main.py --schedule
```

Web 版默认地址为 macOS 的 `http://127.0.0.1:5001`、Windows 的 `http://127.0.0.1:5000`。如果端口已被占用，可以运行 `python main.py --web --port 8000`，再打开 `http://127.0.0.1:8000`。macOS 的 AirPlay 接收器可能会占用 5000 端口。[Flask 端口说明](https://flask.palletsprojects.com/en/stable/server/#address-already-in-use)

## 使用示例

```
你: 帮我分析一下 000001 平安银行
你: 今天大盘怎么样？
你: 哪些板块资金流入最多？
你: 最近有什么财经新闻？
你: 帮我记个笔记：平安银行在12元附近有支撑

# 新功能示例
你: 帮我算一下515290的网格交易方案
你: 如果加仓2000元，成本变成多少？
你: 模拟一下515290每月定投2000的效果
你: 记录一下今天的持仓快照
你: 看看我的收益曲线
你: 今天哪个板块最强？
你: 检测一下板块轮动信号
你: 对比一下银行和证券板块
你: 回测一下515290的均线交叉策略
你: 回测网格策略效果怎么样？
你: 分析一下515290的估值
你: 帮我筛选银行板块低估值股票
你: 用AI分析一下600036招商银行
```

## 配置持仓监控

真实持仓、自选、交易和聊天数据不会提交到 Git。首次使用时复制示例文件：

```bash
# macOS
cp portfolio.example.json portfolio.json
cp watchlist.example.json watchlist.json
cp trades.example.json trades.json
```

```bat
:: Windows（命令提示符）
copy portfolio.example.json portfolio.json
copy watchlist.example.json watchlist.json
copy trades.example.json trades.json
```

然后编辑 `portfolio.json`：

```json
[
  {
    "code": "515290",
    "name": "银行ETF天弘",
    "cost": 1.392,
    "shares": 1000,
    "stop_loss": 1.25,
    "take_profit": 1.60,
    "first_buy_date": "2026-05-11"
  }
]
```

## 配置消息推送（可选）

### Server酱（推送到微信）
1. 访问 https://sct.ftqq.com/ 注册
2. 获取 SendKey
3. 填入 `.env` 的 `SERVERCHAN_KEY`

### 企业微信机器人
1. 在企业微信群中添加机器人
2. 获取 Webhook URL
3. 填入 `.env` 的 `WECHAT_WEBHOOK`

## 项目结构

```
investment-agent/
├── main.py              # 主入口
├── scheduler.py         # 定时任务调度
├── sector_config.py     # 板块配置（ETF映射、关键词）
├── portfolio.json       # 持仓配置
├── .env                 # 配置文件
├── requirements.txt     # 依赖
├── agents/
│   ├── coordinator.py   # 核心 Agent（对话+调度）
│   └── risk_monitor.py  # 风控监控
├── tools/
│   ├── market_data.py       # 行情数据工具
│   ├── news_fetcher.py      # 新闻抓取工具
│   ├── notify.py            # 消息推送工具
│   ├── position_manager.py  # 仓位管理（网格/加仓/定投）
│   ├── portfolio_tracker.py # 收益追踪（快照/曲线/统计）
│   ├── sector_rotation.py   # 板块轮动（强弱/信号/对比）
│   ├── backtest.py          # 策略回测（均线/网格/定投）
│   └── stock_screener.py    # 选股估值（PE-PB/筛选/AI分析）
├── knowledge/
│   └── rag.py           # RAG 知识库
├── web/
│   ├── app.py           # Flask Web 服务
│   └── templates/
│       └── index.html   # Web 界面
└── data/
    ├── chromadb/            # 知识库存储
    └── portfolio_history.json  # 收益历史记录
```

## Web API 新接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/profit-curve` | GET | 收益曲线数据 (参数: period=week/month/year/all) |
| `/api/profit-curve/record` | POST | 手动记录今日快照 |
| `/api/sector-rotation` | GET | 板块轮动排名 |
| `/api/sector-rotation/history` | GET | 板块近期走势对比 |
| `/api/backtest` | POST | 运行回测 (strategy=ma/grid/dca) |
| `/api/valuation` | GET | 估值分析 (参数: symbol) |
| `/api/screener` | GET | 低估值筛选 (参数: sector) |
| `/api/position/grid` | POST | 网格交易方案 |
| `/api/position/add-calc` | POST | 加仓计算 |

## 定时任务

运行 `python main.py --schedule` 后，按北京时间和 A 股交易日历执行。交易日历不可用时跳过自动任务。

| 时间 | 任务 |
|------|------|
| 交易日 9:20 | 盘前市场概览 |
| 交易日 09:30–11:30、13:00–15:00，每 30 分钟 | 风险检查 |
| 交易日 15:10 | 记录持仓快照（收益曲线数据源）|
| 交易日 17:00 | 生成每日投资简报 |

## 进阶扩展

- 添加更多数据源（同花顺、雪球等）
- 接入量化回测框架（backtrader）
- 增加 AI 选股策略
- 接入交易接口（模拟盘）
- 部署到服务器 24 小时运行
