import React, { useEffect, useState } from 'react';
import {
  Row,
  Col,
  Card,
  Statistic,
  Table,
  Progress,
  Tag,
  Space,
  Button,
  Typography,
  Alert,
  Spin,
  Tooltip,
  Select,
  DatePicker,
  Tabs,
  Switch,
} from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  DollarOutlined,
  SwapOutlined,
  TrophyOutlined,
  WarningOutlined,
  ReloadOutlined,
  EyeOutlined,
  DashboardOutlined,
  SettingOutlined,
  ShieldOutlined,
} from '@ant-design/icons';
import { useAppSelector, useAppDispatch } from '../../hooks/redux';
import { fetchDashboardData } from '../../store/slices/dashboardSlice';
import PriceChart from '../../components/Charts/PriceChart';
import ArbitrageChart from '../../components/Charts/ArbitrageChart';
import PerformanceMetrics from '../../components/Dashboard/PerformanceMetrics';
import RecentTrades from '../../components/Dashboard/RecentTrades';
import TopOpportunities from '../../components/Dashboard/TopOpportunities';
import RealTimeDataPanel from '../../components/RealTimeData/RealTimeDataPanel';
import StrategyConfigPanel from '../../components/Strategy/StrategyConfigPanel';
import RiskMonitorDashboard from '../../components/Risk/RiskMonitorDashboard';
import UnifiedTransferPanel from '../../components/Transfer/UnifiedTransferPanel';
import './Dashboard.css';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;
const { TabPane } = Tabs;

interface DashboardStats {
  totalBalance: number;
  totalProfit: number;
  profitChange: number;
  activeStrategies: number;
  successRate: number;
  arbitrageOpportunities: number;
}

interface ArbitrageOpportunity {
  id: string;
  symbol: string;
  buyExchange: string;
  sellExchange: string;
  profit: number;
  profitPercent: number;
  volume: number;
  status: 'active' | 'executed' | 'expired';
  timestamp: string;
}

const Dashboard: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector(state => state.auth);
  const { isDarkMode } = useAppSelector(state => state.app);
  
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [timeRange, setTimeRange] = useState('24h');
  const [activeTab, setActiveTab] = useState('overview');
  const [compactMode, setCompactMode] = useState(false);
  const [dashboardStats, setDashboardStats] = useState<DashboardStats>({
    totalBalance: 0,
    totalProfit: 0,
    profitChange: 0,
    activeStrategies: 0,
    successRate: 0,
    arbitrageOpportunities: 0,
  });
  
  const [recentOpportunities, setRecentOpportunities] = useState<ArbitrageOpportunity[]>([]);
  
  useEffect(() => {
    loadDashboardData();
    
    // Set up auto-refresh
    const interval = setInterval(() => {
      loadDashboardData(true);
    }, 30000); // Refresh every 30 seconds
    
    return () => clearInterval(interval);
  }, [timeRange]);
  
  const loadDashboardData = async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    
    try {
      // Simulate API calls - replace with actual API calls
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Mock data - replace with actual API responses
      setDashboardStats({
        totalBalance: 125430.50,
        totalProfit: 8750.25,
        profitChange: 12.5,
        activeStrategies: 5,
        successRate: 87.3,
        arbitrageOpportunities: 23,
      });
      
      setRecentOpportunities([
        {
          id: '1',
          symbol: 'BTC/USDT',
          buyExchange: 'Binance',
          sellExchange: 'OKX',
          profit: 125.50,
          profitPercent: 0.28,
          volume: 1.5,
          status: 'active',
          timestamp: new Date().toISOString(),
        },
        {
          id: '2',
          symbol: 'ETH/USDT',
          buyExchange: 'Huobi',
          sellExchange: 'Binance',
          profit: 89.30,
          profitPercent: 0.15,
          volume: 5.2,
          status: 'active',
          timestamp: new Date().toISOString(),
        },
        {
          id: '3',
          symbol: 'BNB/USDT',
          buyExchange: 'OKX',
          sellExchange: 'Huobi',
          profit: 45.80,
          profitPercent: 0.12,
          volume: 12.8,
          status: 'executed',
          timestamp: new Date().toISOString(),
        },
      ]);
      
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };
  
  const handleRefresh = () => {
    loadDashboardData(true);
  };
  
  const opportunityColumns = [
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Text strong>{symbol}</Text>,
    },
    {
      title: '买入交易所',
      dataIndex: 'buyExchange',
      key: 'buyExchange',
    },
    {
      title: '卖出交易所',
      dataIndex: 'sellExchange',
      key: 'sellExchange',
    },
    {
      title: '预期利润',
      dataIndex: 'profit',
      key: 'profit',
      render: (profit: number, record: ArbitrageOpportunity) => (
        <Space direction="vertical" size={0}>
          <Text strong>${profit.toFixed(2)}</Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {record.profitPercent.toFixed(2)}%
          </Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusConfig = {
          active: { color: 'green', text: '活跃' },
          executed: { color: 'blue', text: '已执行' },
          expired: { color: 'red', text: '已过期' },
        };
        const config = statusConfig[status as keyof typeof statusConfig];
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_record, record: ArbitrageOpportunity) => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => console.log('View opportunity:', record.id)}
        >
          查看详情
        </Button>
      ),
    },
  ];
  
  if (loading) {
    return (
      <div className="dashboard-loading">
        <Spin size="large" />
        <Text>加载仪表板数据...</Text>
      </div>
    );
  }
  
  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <div className="header-left">
            <Title level={2} style={{ margin: 0 }}>
              欢迎回来，{user?.username || '用户'}
            </Title>
            <Text type="secondary">
              这是您的交易概览和套利机会监控面板
            </Text>
          </div>
          
          <div className="header-right">
            <Space>
              <Switch
                checkedChildren="紧凑"
                unCheckedChildren="标准"
                checked={compactMode}
                onChange={setCompactMode}
              />
              
              <Select
                value={timeRange}
                onChange={setTimeRange}
                style={{ width: 120 }}
                options={[
                  { label: '24小时', value: '24h' },
                  { label: '7天', value: '7d' },
                  { label: '30天', value: '30d' },
                  { label: '90天', value: '90d' },
                ]}
              />
              
              <Button
                icon={<ReloadOutlined spin={refreshing} />}
                onClick={handleRefresh}
                loading={refreshing}
              >
                刷新
              </Button>
            </Space>
          </div>
        </div>
      </div>
      
      {/* Main Content Tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="dashboard-tabs"
        size={compactMode ? 'small' : 'middle'}
      >
        <TabPane
          tab={
            <span>
              <DashboardOutlined />
              概览
            </span>
          }
          key="overview"
        >
          {/* Stats Cards */}
          <Row gutter={[16, 16]} className="stats-row">
            <Col xs={24} sm={12} lg={6}>
              <Card className="stat-card" size={compactMode ? 'small' : 'default'}>
                <Statistic
                  title="总资产"
                  value={dashboardStats.totalBalance}
                  precision={2}
                  prefix={<DollarOutlined />}
                  suffix="USDT"
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            
            <Col xs={24} sm={12} lg={6}>
              <Card className="stat-card" size={compactMode ? 'small' : 'default'}>
                <Statistic
                  title="总收益"
                  value={dashboardStats.totalProfit}
                  precision={2}
                  prefix={<TrophyOutlined />}
                  suffix="USDT"
                  valueStyle={{ color: '#52c41a' }}
                />
                <div className="stat-change">
                  <Text
                    type={dashboardStats.profitChange >= 0 ? 'success' : 'danger'}
                    style={{ fontSize: '12px' }}
                  >
                    {dashboardStats.profitChange >= 0 ? (
                      <ArrowUpOutlined />
                    ) : (
                      <ArrowDownOutlined />
                    )}
                    {Math.abs(dashboardStats.profitChange)}% 今日
                  </Text>
                </div>
              </Card>
            </Col>
            
            <Col xs={24} sm={12} lg={6}>
              <Card className="stat-card" size={compactMode ? 'small' : 'default'}>
                <Statistic
                  title="活跃策略"
                  value={dashboardStats.activeStrategies}
                  prefix={<SwapOutlined />}
                  valueStyle={{ color: '#722ed1' }}
                />
                <div className="stat-extra">
                  <Progress
                    percent={dashboardStats.successRate}
                    size="small"
                    format={(percent) => `成功率 ${percent}%`}
                  />
                </div>
              </Card>
            </Col>
            
            <Col xs={24} sm={12} lg={6}>
              <Card className="stat-card" size={compactMode ? 'small' : 'default'}>
                <Statistic
                  title="套利机会"
                  value={dashboardStats.arbitrageOpportunities}
                  prefix={<WarningOutlined />}
                  valueStyle={{ color: '#fa8c16' }}
                />
                <div className="stat-extra">
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    实时监控中
                  </Text>
                </div>
              </Card>
            </Col>
          </Row>
      
          {/* Charts Row */}
          <Row gutter={[16, 16]} className="charts-row">
            <Col xs={24} lg={16}>
              <Card title="价格趋势" className="chart-card" size={compactMode ? 'small' : 'default'}>
                <PriceChart timeRange={timeRange} />
              </Card>
            </Col>
            
            <Col xs={24} lg={8}>
              <Card title="套利收益" className="chart-card" size={compactMode ? 'small' : 'default'}>
                <ArbitrageChart timeRange={timeRange} />
              </Card>
            </Col>
          </Row>
          
          {/* Content Row */}
          <Row gutter={[16, 16]} className="content-row">
            <Col xs={24} lg={12}>
              <Card
                title="最新套利机会"
                className="opportunities-card"
                size={compactMode ? 'small' : 'default'}
                extra={
                  <Button type="link" onClick={() => console.log('View all opportunities')}>
                    查看全部
                  </Button>
                }
              >
                <Table
                  dataSource={recentOpportunities}
                  columns={opportunityColumns}
                  pagination={false}
                  size={compactMode ? 'small' : 'middle'}
                  rowKey="id"
                />
              </Card>
            </Col>
            
            <Col xs={24} lg={12}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {/* Performance Metrics */}
                <Card title="性能指标" className="metrics-card" size={compactMode ? 'small' : 'default'}>
                  <PerformanceMetrics timeRange={timeRange} />
                </Card>
                
                {/* Recent Trades */}
                <Card title="最近交易" className="trades-card" size={compactMode ? 'small' : 'default'}>
                  <RecentTrades limit={5} />
                </Card>
              </Space>
            </Col>
          </Row>
        </TabPane>
        
        <TabPane
          tab={
            <span>
              <DashboardOutlined />
              实时数据
            </span>
          }
          key="realtime"
        >
          <RealTimeDataPanel />
        </TabPane>
        
        <TabPane
          tab={
            <span>
              <SettingOutlined />
              策略配置
            </span>
          }
          key="strategy"
        >
          <StrategyConfigPanel />
        </TabPane>
        
        <TabPane
          tab={
            <span>
              <ShieldOutlined />
              风险监控
            </span>
          }
          key="risk"
        >
          <RiskMonitorDashboard />
        </TabPane>
        
        <TabPane
          tab={
            <span>
              <SwapOutlined />
              资金调度
            </span>
          }
          key="transfer"
        >
          <UnifiedTransferPanel />
        </TabPane>
      </Tabs>
      
      {/* Alerts */}
      {dashboardStats.arbitrageOpportunities > 20 && (
        <Alert
          message="高套利机会警告"
          description={`当前检测到 ${dashboardStats.arbitrageOpportunities} 个套利机会，建议及时关注市场动态。`}
          type="warning"
          showIcon
          closable
          className="dashboard-alert"
        />
      )}
    </div>
  );
};

export default Dashboard;