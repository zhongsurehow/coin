import React, { useState, useEffect } from 'react';
import {
  Card,
  Row,
  Col,
  Progress,
  Statistic,
  Alert,
  Table,
  Tag,
  Space,
  Typography,
  Button,
  Select,
  DatePicker,
  Tooltip,
  Badge,
  Timeline,
  Divider,
  Switch,
  notification,
} from 'antd';
import {
  WarningOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  TrendingUpOutlined,
  TrendingDownOutlined,
  DollarOutlined,
  PercentageOutlined,
  ClockCircleOutlined,
  ShieldOutlined,
  AlertOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Line, Gauge, Column } from '@ant-design/plots';
import './RiskMonitorDashboard.css';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

interface RiskMetric {
  id: string;
  name: string;
  value: number;
  threshold: number;
  status: 'safe' | 'warning' | 'danger';
  trend: 'up' | 'down' | 'stable';
  description: string;
}

interface RiskEvent {
  id: string;
  type: 'position_limit' | 'loss_limit' | 'volatility' | 'liquidity' | 'system';
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  timestamp: string;
  resolved: boolean;
  strategy?: string;
  exchange?: string;
}

interface PositionRisk {
  symbol: string;
  exchange: string;
  position: number;
  value: number;
  riskScore: number;
  exposure: number;
  pnl: number;
  maxDrawdown: number;
}

interface SystemHealth {
  api_latency: number;
  memory_usage: number;
  cpu_usage: number;
  disk_usage: number;
  network_status: 'good' | 'poor' | 'disconnected';
  last_update: string;
}

const RiskMonitorDashboard: React.FC = () => {
  const [riskMetrics, setRiskMetrics] = useState<RiskMetric[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEvent[]>([]);
  const [positionRisks, setPositionRisks] = useState<PositionRisk[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [selectedTimeRange, setSelectedTimeRange] = useState('24h');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  
  // 历史数据用于图表
  const [riskTrendData, setRiskTrendData] = useState<any[]>([]);
  const [exposureData, setExposureData] = useState<any[]>([]);

  // 模拟数据初始化
  useEffect(() => {
    const mockRiskMetrics: RiskMetric[] = [
      {
        id: 'total_exposure',
        name: '总风险敞口',
        value: 75.5,
        threshold: 80,
        status: 'warning',
        trend: 'up',
        description: '当前总风险敞口占可用资金的75.5%',
      },
      {
        id: 'daily_loss',
        name: '日亏损率',
        value: 2.3,
        threshold: 5,
        status: 'safe',
        trend: 'down',
        description: '今日亏损占总资金的2.3%',
      },
      {
        id: 'position_concentration',
        name: '仓位集中度',
        value: 45.2,
        threshold: 50,
        status: 'safe',
        trend: 'stable',
        description: '最大单一仓位占总资金的45.2%',
      },
      {
        id: 'volatility_risk',
        name: '波动率风险',
        value: 85.7,
        threshold: 70,
        status: 'danger',
        trend: 'up',
        description: '市场波动率超出正常范围',
      },
      {
        id: 'liquidity_risk',
        name: '流动性风险',
        value: 25.8,
        threshold: 30,
        status: 'safe',
        trend: 'down',
        description: '当前流动性状况良好',
      },
      {
        id: 'correlation_risk',
        name: '相关性风险',
        value: 68.4,
        threshold: 75,
        status: 'warning',
        trend: 'up',
        description: '资产间相关性较高',
      },
    ];

    const mockRiskEvents: RiskEvent[] = [
      {
        id: '1',
        type: 'volatility',
        severity: 'high',
        message: 'BTC/USDT 波动率超过阈值 15%',
        timestamp: new Date(Date.now() - 300000).toISOString(),
        resolved: false,
        strategy: 'BTC套利策略',
        exchange: 'binance',
      },
      {
        id: '2',
        type: 'position_limit',
        severity: 'medium',
        message: 'ETH/USDT 仓位接近上限',
        timestamp: new Date(Date.now() - 600000).toISOString(),
        resolved: true,
        strategy: 'ETH网格策略',
        exchange: 'okx',
      },
      {
        id: '3',
        type: 'loss_limit',
        severity: 'critical',
        message: '日亏损接近限额',
        timestamp: new Date(Date.now() - 900000).toISOString(),
        resolved: false,
      },
      {
        id: '4',
        type: 'liquidity',
        severity: 'low',
        message: 'ADA/USDT 流动性不足',
        timestamp: new Date(Date.now() - 1200000).toISOString(),
        resolved: true,
        exchange: 'huobi',
      },
    ];

    const mockPositionRisks: PositionRisk[] = [
      {
        symbol: 'BTC/USDT',
        exchange: 'binance',
        position: 0.5,
        value: 21500,
        riskScore: 75,
        exposure: 15.2,
        pnl: 340.50,
        maxDrawdown: 5.8,
      },
      {
        symbol: 'ETH/USDT',
        exchange: 'okx',
        position: 8.2,
        value: 18900,
        riskScore: 62,
        exposure: 13.4,
        pnl: -125.30,
        maxDrawdown: 3.2,
      },
      {
        symbol: 'BNB/USDT',
        exchange: 'binance',
        position: 45.6,
        value: 12800,
        riskScore: 45,
        exposure: 9.1,
        pnl: 89.20,
        maxDrawdown: 2.1,
      },
    ];

    const mockSystemHealth: SystemHealth = {
      api_latency: 45,
      memory_usage: 68.5,
      cpu_usage: 42.3,
      disk_usage: 78.9,
      network_status: 'good',
      last_update: new Date().toISOString(),
    };

    // 生成趋势数据
    const generateTrendData = () => {
      const data = [];
      for (let i = 23; i >= 0; i--) {
        const time = new Date(Date.now() - i * 3600000).toISOString();
        data.push({
          time,
          exposure: 70 + Math.random() * 20,
          volatility: 60 + Math.random() * 30,
          liquidity: 20 + Math.random() * 20,
        });
      }
      return data;
    };

    // 生成敞口分布数据
    const generateExposureData = () => [
      { exchange: 'Binance', exposure: 45.2 },
      { exchange: 'OKX', exposure: 28.7 },
      { exchange: 'Huobi', exposure: 15.3 },
      { exchange: 'Coinbase', exposure: 10.8 },
    ];

    setRiskMetrics(mockRiskMetrics);
    setRiskEvents(mockRiskEvents);
    setPositionRisks(mockPositionRisks);
    setSystemHealth(mockSystemHealth);
    setRiskTrendData(generateTrendData());
    setExposureData(generateExposureData());
  }, []);

  // 自动刷新
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      // 模拟数据更新
      setRiskMetrics(prev => prev.map(metric => ({
        ...metric,
        value: Math.max(0, metric.value + (Math.random() - 0.5) * 5),
      })));

      if (systemHealth) {
        setSystemHealth(prev => prev ? {
          ...prev,
          api_latency: Math.max(10, prev.api_latency + (Math.random() - 0.5) * 10),
          memory_usage: Math.max(0, Math.min(100, prev.memory_usage + (Math.random() - 0.5) * 5)),
          cpu_usage: Math.max(0, Math.min(100, prev.cpu_usage + (Math.random() - 0.5) * 10)),
          last_update: new Date().toISOString(),
        } : null);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [autoRefresh, systemHealth]);

  // 风险警报
  useEffect(() => {
    if (!alertsEnabled) return;

    const criticalMetrics = riskMetrics.filter(metric => metric.status === 'danger');
    const warningMetrics = riskMetrics.filter(metric => metric.status === 'warning');

    if (criticalMetrics.length > 0) {
      notification.error({
        message: '严重风险警告',
        description: `${criticalMetrics.length} 个风险指标超过危险阈值`,
        duration: 0,
      });
    } else if (warningMetrics.length > 0) {
      notification.warning({
        message: '风险提醒',
        description: `${warningMetrics.length} 个风险指标需要关注`,
        duration: 5,
      });
    }
  }, [riskMetrics, alertsEnabled]);

  const getRiskColor = (status: string) => {
    switch (status) {
      case 'safe': return '#52c41a';
      case 'warning': return '#fa8c16';
      case 'danger': return '#ff4d4f';
      default: return '#d9d9d9';
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'low': return 'blue';
      case 'medium': return 'orange';
      case 'high': return 'red';
      case 'critical': return 'purple';
      default: return 'default';
    }
  };

  const riskEventColumns = [
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => {
        const typeMap = {
          position_limit: '仓位限制',
          loss_limit: '亏损限制',
          volatility: '波动率',
          liquidity: '流动性',
          system: '系统',
        };
        return <Tag>{typeMap[type as keyof typeof typeMap] || type}</Tag>;
      },
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={getSeverityColor(severity)}>
          {severity.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '策略/交易所',
      key: 'source',
      render: (record: RiskEvent) => (
        <Space direction="vertical" size="small">
          {record.strategy && <Tag color="blue">{record.strategy}</Tag>}
          {record.exchange && <Tag color="green">{record.exchange.toUpperCase()}</Tag>}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'resolved',
      key: 'resolved',
      render: (resolved: boolean) => (
        <Badge
          status={resolved ? 'success' : 'error'}
          text={resolved ? '已解决' : '待处理'}
        />
      ),
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (timestamp: string) => (
        <Text>{new Date(timestamp).toLocaleString()}</Text>
      ),
    },
  ];

  const positionRiskColumns = [
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Text strong>{symbol}</Text>,
    },
    {
      title: '交易所',
      dataIndex: 'exchange',
      key: 'exchange',
      render: (exchange: string) => <Tag color="blue">{exchange.toUpperCase()}</Tag>,
    },
    {
      title: '仓位',
      dataIndex: 'position',
      key: 'position',
      render: (position: number) => <Text>{position.toFixed(4)}</Text>,
    },
    {
      title: '价值 (USDT)',
      dataIndex: 'value',
      key: 'value',
      render: (value: number) => <Text>${value.toLocaleString()}</Text>,
    },
    {
      title: '风险评分',
      dataIndex: 'riskScore',
      key: 'riskScore',
      render: (score: number) => (
        <Progress
          percent={score}
          size="small"
          status={score > 80 ? 'exception' : score > 60 ? 'normal' : 'success'}
          format={(percent) => `${percent}`}
        />
      ),
    },
    {
      title: '敞口 (%)',
      dataIndex: 'exposure',
      key: 'exposure',
      render: (exposure: number) => <Text>{exposure.toFixed(1)}%</Text>,
    },
    {
      title: 'PnL (USDT)',
      dataIndex: 'pnl',
      key: 'pnl',
      render: (pnl: number) => (
        <Text type={pnl >= 0 ? 'success' : 'danger'}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </Text>
      ),
    },
    {
      title: '最大回撤 (%)',
      dataIndex: 'maxDrawdown',
      key: 'maxDrawdown',
      render: (drawdown: number) => (
        <Text type="danger">{drawdown.toFixed(1)}%</Text>
      ),
    },
  ];

  const trendConfig = {
    data: riskTrendData,
    xField: 'time',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
  };

  const exposureConfig = {
    data: exposureData,
    xField: 'exchange',
    yField: 'exposure',
    color: '#1890ff',
    columnStyle: {
      radius: [4, 4, 0, 0],
    },
  };

  return (
    <div className="risk-monitor-dashboard">
      {/* 控制面板 */}
      <Card className="control-panel" size="small">
        <Row gutter={16} align="middle">
          <Col>
            <Title level={4} style={{ margin: 0, color: 'white' }}>风险监控仪表板</Title>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Text style={{ color: 'white' }}>自动刷新</Text>
              <Switch
                checked={autoRefresh}
                onChange={setAutoRefresh}
                size="small"
              />
            </Space>
          </Col>
          <Col>
            <Space>
              <Text style={{ color: 'white' }}>风险警报</Text>
              <Switch
                checked={alertsEnabled}
                onChange={setAlertsEnabled}
                size="small"
              />
            </Space>
          </Col>
          <Col>
            <Select
              value={selectedTimeRange}
              onChange={setSelectedTimeRange}
              size="small"
              style={{ width: 100 }}
            >
              <Option value="1h">1小时</Option>
              <Option value="24h">24小时</Option>
              <Option value="7d">7天</Option>
              <Option value="30d">30天</Option>
            </Select>
          </Col>
          <Col>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              style={{ color: 'white', borderColor: 'white' }}
            >
              刷新
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 风险指标卡片 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        {riskMetrics.map((metric) => (
          <Col span={4} key={metric.id}>
            <Card className="risk-metric-card">
              <div className="metric-header">
                <Text strong>{metric.name}</Text>
                <Tooltip title={metric.description}>
                  <Badge
                    status={metric.status === 'safe' ? 'success' : metric.status === 'warning' ? 'warning' : 'error'}
                  />
                </Tooltip>
              </div>
              <div className="metric-value">
                <Statistic
                  value={metric.value}
                  precision={1}
                  suffix="%"
                  valueStyle={{ 
                    color: getRiskColor(metric.status),
                    fontSize: '24px',
                    fontWeight: 'bold'
                  }}
                />
              </div>
              <div className="metric-progress">
                <Progress
                  percent={(metric.value / metric.threshold) * 100}
                  strokeColor={getRiskColor(metric.status)}
                  showInfo={false}
                  size="small"
                />
              </div>
              <div className="metric-trend">
                <Space>
                  {metric.trend === 'up' ? (
                    <TrendingUpOutlined style={{ color: '#ff4d4f' }} />
                  ) : metric.trend === 'down' ? (
                    <TrendingDownOutlined style={{ color: '#52c41a' }} />
                  ) : (
                    <Text>-</Text>
                  )}
                  <Text type="secondary">阈值: {metric.threshold}%</Text>
                </Space>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 系统健康状态 */}
      {systemHealth && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={6}>
            <Card title="API延迟" size="small">
              <Gauge
                percent={Math.min(systemHealth.api_latency / 200, 1)}
                color={['#30BF78', '#FAAD14', '#F4664A']}
                innerRadius={0.75}
                range={{ ticks: [0, 1], color: ['l(0) 0:#30BF78 0.5:#FAAD14 1:#F4664A'] }}
                indicator={{
                  pointer: { style: { stroke: '#D0D0D0' } },
                  pin: { style: { stroke: '#D0D0D0' } },
                }}
                statistic={{
                  content: {
                    style: { fontSize: '16px', lineHeight: '16px', color: '#4B535E' },
                    formatter: () => `${systemHealth.api_latency.toFixed(0)}ms`,
                  },
                }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card title="内存使用" size="small">
              <Progress
                type="circle"
                percent={systemHealth.memory_usage}
                format={(percent) => `${percent?.toFixed(1)}%`}
                strokeColor={systemHealth.memory_usage > 80 ? '#ff4d4f' : '#1890ff'}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card title="CPU使用" size="small">
              <Progress
                type="circle"
                percent={systemHealth.cpu_usage}
                format={(percent) => `${percent?.toFixed(1)}%`}
                strokeColor={systemHealth.cpu_usage > 80 ? '#ff4d4f' : '#52c41a'}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card title="磁盘使用" size="small">
              <Progress
                type="circle"
                percent={systemHealth.disk_usage}
                format={(percent) => `${percent?.toFixed(1)}%`}
                strokeColor={systemHealth.disk_usage > 90 ? '#ff4d4f' : '#fa8c16'}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 图表区域 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={16}>
          <Card title="风险趋势" size="small">
            <Line {...trendConfig} height={300} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="敞口分布" size="small">
            <Column {...exposureConfig} height={300} />
          </Card>
        </Col>
      </Row>

      {/* 风险事件和仓位风险 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={14}>
          <Card title="风险事件" size="small">
            <Table
              columns={riskEventColumns}
              dataSource={riskEvents}
              rowKey="id"
              pagination={{ pageSize: 5 }}
              size="small"
            />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="仓位风险" size="small">
            <Table
              columns={positionRiskColumns}
              dataSource={positionRisks}
              rowKey={(record) => `${record.exchange}-${record.symbol}`}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 风险事件时间线 */}
      <Row style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="最近风险事件" size="small">
            <Timeline>
              {riskEvents.slice(0, 5).map((event) => (
                <Timeline.Item
                  key={event.id}
                  color={event.resolved ? 'green' : getSeverityColor(event.severity)}
                  dot={event.resolved ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                >
                  <div>
                    <Space>
                      <Tag color={getSeverityColor(event.severity)}>
                        {event.severity.toUpperCase()}
                      </Tag>
                      <Text strong>{event.message}</Text>
                      {event.resolved && <Tag color="green">已解决</Tag>}
                    </Space>
                    <br />
                    <Text type="secondary">
                      {new Date(event.timestamp).toLocaleString()}
                      {event.strategy && ` - ${event.strategy}`}
                      {event.exchange && ` - ${event.exchange.toUpperCase()}`}
                    </Text>
                  </div>
                </Timeline.Item>
              ))}
            </Timeline>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default RiskMonitorDashboard;