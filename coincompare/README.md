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

## 快速开始

### 环境要求

- Docker & Docker Compose

### 使用 Docker 启动 (推荐)

#### 1. 克隆项目
```bash
git clone https://github.com/your-repo/coincompare.git
cd coincompare
```
*请注意: 上述命令会带您进入项目根目录, 您应该能在此目录中看到 `docker-compose.yml` 文件。*

#### 2. 构建基础镜像 (必需步骤)
由于网络原因，直接构建可能会失败。我们提供了一个预构建的方案。请在项目根目录运行以下命令，首先构建包含所有系统依赖的基础镜像：
```bash
docker build -t juleseng/coincompare-base:1.0.0 -f coincompare/backend/prebuild.Dockerfile .
```
**注意:** 此命令只需要在您第一次设置项目或 `prebuild.Dockerfile` 发生更改时运行一次。

#### 3. 启动所有服务
基础镜像构建成功后，您现在可以一键启动所有应用服务：
```bash
docker compose up -d --build
```

#### 4. 查看服务

查看所有服务的运行状态：
```bash
docker compose ps
```

查看实时日志：
```bash
docker compose logs -f
```

### 访问应用

所有服务启动后，可以通过以下地址访问：

- **应用主页**: http://localhost
- **后端API**: http://localhost/api/v1
- **API文档**: http://localhost/docs
- **监控面板**: http://localhost:3001 (Grafana)

### 手动安装 (可选)

如果不想使用 Docker，也可以手动设置开发环境。

#### 1. 后端设置

```bash
# 进入后端目录
cd coincompare/backend

# (按照原有步骤设置)
...
```

#### 2. 前端设置

```bash
# 进入前端目录
cd coincompare/frontend

# (按照原有步骤设置)
...
```

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
.
├── coincompare/
│   ├── backend/            # 后端服务 (FastAPI)
│   ├── frontend/           # 前端应用 (React)
│   ├── monitoring/         # Prometheus 配置
│   └── nginx/              # Nginx 配置
├── docker-compose.yml      # Docker Compose 配置文件
└── README.md               # 项目文档
```

## 关于构建过程 (About the Build Process)

为了解决在某些网络环境下系统依赖包 (`apt-get`) 安装不稳定的问题，本项目的后端服务采用了一个预构建的 Docker 基础镜像 (`juleseng/coincompare-base:1.0.0`)。

这个基础镜像包含了所有必需的系统级依赖。这样做的好处是，在您本地构建时，无需再从 Debian 的服务器上下载这些包，从而大大提高了构建的成功率和速度。

如果您需要修改基础系统依赖，可以参考 `coincompare/backend/prebuild.Dockerfile` 文件。维护者可以使用它来构建和推送新版本的基础镜像。

## 注意事项

- 价格数据仅供参考，不构成投资建议
- 投资有风险，请谨慎操作
- 确保API密钥安全，定期更换
- 建议在测试环境充分验证后再部署到生产环境