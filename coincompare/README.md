# CoinCompare - 高级加密货币套利交易平台

## 项目概述

CoinCompare 是一个现代化的加密货币套利交易平台，集成了 Hummingbot 自动化交易引擎，提供实时市场数据监控、智能套利机会检测、自动化策略执行和完善的充提管理功能。

### 主要特性

- 🚀 **实时套利监控** - 多交易所价格监控和套利机会检测
- 🤖 **Hummingbot 集成** - 自动化策略执行和管理
- 💰 **充提合一** - 跨交易所资金调度和最优路径计算
- 📊 **高级分析** - 实时数据可视化和性能分析
- 🔒 **安全可靠** - 企业级安全措施和风险控制
- 🎨 **现代界面** - 响应式设计和直观的用户体验

## 技术架构

### 后端技术栈

- **框架**: FastAPI (Python 3.9+)
- **数据库**: PostgreSQL + Redis + InfluxDB
- **异步处理**: asyncio + Celery
- **API文档**: Swagger/OpenAPI
- **监控**: Prometheus + Grafana
- **部署**: Docker + Docker Compose

### 前端技术栈

- **框架**: React 18 + TypeScript
- **状态管理**: Redux Toolkit + Zustand
- **UI组件**: Ant Design
- **图表**: ECharts + Chart.js
- **构建工具**: Create React App
- **样式**: CSS Modules + Styled Components

### 集成服务

- **交易所**: Binance, OKX, Huobi
- **交易引擎**: Hummingbot
- **数据源**: CoinGecko, CoinMarketCap
- **通知**: Email, Webhook, WebSocket

### ⚠️ 安全警告

**请注意：** 为便于本地开发快速启动，本项目的 `docker-compose.yml` 文件中包含了**硬编码的机密信息**（例如，数据库密码、API密钥等）。

**请勿在生产环境中使用此配置。**

在部署到生产环境之前，强烈建议您将这些机密信息外部化，例如使用环境变量或专门的密钥管理服务。

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 16+
- PostgreSQL 13+
- Redis 6+
- Docker & Docker Compose (可选)

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/your-repo/coincompare.git
cd coincompare
```

#### 2. 后端设置

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入实际配置

# 初始化数据库
python -c "from app.core.database import create_tables; import asyncio; asyncio.run(create_tables())"

# 启动后端服务
python run.py
```

#### 3. 前端设置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm start
```

#### 4. 使用 Docker (推荐)

```bash
# 构建和启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 访问应用

- **前端界面**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **监控面板**: http://localhost:3001 (Grafana)

## 功能模块

### 1. 仪表板

- 实时资产概览
- 收益统计和趋势
- 活跃策略监控
- 套利机会提醒

### 2. 套利交易

- 多交易所价格监控
- 实时套利机会检测
- 自动化交易执行
- 收益分析和报告

### 3. 充值提现

- 多交易所充值地址管理
- 智能提现路径规划
- 实时状态监控
- 手续费优化

### 4. 策略管理

- Hummingbot 策略配置
- 策略性能监控
- 风险参数设置
- 回测和优化

### 5. 市场数据

- 实时价格图表
- 深度图和K线图
- 交易量分析
- 市场情绪指标

### 6. 系统设置

- 用户账户管理
- API密钥配置
- 风险控制设置
- 通知偏好设置

## 文件结构

```
coincompare/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API路由
│   │   ├── models/         # 数据模型
│   │   ├── services/       # 业务服务
│   │   ├── config.py       # 配置文件
│   │   ├── database.py     # 数据库连接
│   │   └── main.py         # FastAPI应用
│   ├── requirements.txt    # Python依赖
│   ├── .env.example       # 环境变量模板
│   └── run.py             # 启动脚本
├── frontend/               # 前端应用
│   ├── src/
│   │   ├── components/     # React组件
│   │   ├── pages/         # 页面组件
│   │   ├── store/         # Redux状态管理
│   │   └── App.tsx        # 主应用组件
│   └── package.json       # Node.js依赖
├── index.html             # 原始静态页面
├── script.js              # 原始JavaScript
├── styles.css             # 原始样式
└── README.md              # 项目文档
```

## 注意事项

- 价格数据仅供参考，不构成投资建议
- 投资有风险，请谨慎操作
- 确保API密钥安全，定期更换
- 建议在测试环境充分验证后再部署到生产环境