import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Row,
  Col,
  Input,
  InputNumber,
  Select,
  Switch,
  Button,
  Table,
  Tag,
  Space,
  Modal,
  Drawer,
  Tabs,
  Alert,
  Progress,
  Statistic,
  Typography,
  Divider,
  Tooltip,
  Popconfirm,
  message,
  notification,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  SettingOutlined,
  TrendingUpOutlined,
  DollarOutlined,
  PercentageOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import './StrategyConfigPanel.css';

const { Title, Text } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;

interface StrategyConfig {
  id: string;
  name: string;
  type: 'arbitrage' | 'grid' | 'dca' | 'custom';
  status: 'active' | 'paused' | 'stopped';
  exchanges: string[];
  symbols: string[];
  minProfitPercent: number;
  maxPositionSize: number;
  riskLevel: 'low' | 'medium' | 'high';
  autoExecute: boolean;
  stopLoss?: number;
  takeProfit?: number;
  maxDailyTrades?: number;
  cooldownPeriod?: number;
  createdAt: string;
  updatedAt: string;
  performance?: {
    totalTrades: number;
    successRate: number;
    totalProfit: number;
    avgProfitPercent: number;
    maxDrawdown: number;
  };
}

interface RiskSettings {
  maxDailyLoss: number;
  maxPositionPercent: number;
  enableStopLoss: boolean;
  enableTakeProfit: boolean;
  maxConcurrentTrades: number;
  minLiquidity: number;
}

interface NotificationSettings {
  enableEmail: boolean;
  enableSMS: boolean;
  enableWebhook: boolean;
  profitThreshold: number;
  lossThreshold: number;
  webhookUrl?: string;
}

const StrategyConfigPanel: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyConfig[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyConfig | null>(null);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isDrawerVisible, setIsDrawerVisible] = useState(false);
  const [activeTab, setActiveTab] = useState('strategies');
  const [form] = Form.useForm();
  const [riskForm] = Form.useForm();
  const [notificationForm] = Form.useForm();
  
  const [riskSettings, setRiskSettings] = useState<RiskSettings>({
    maxDailyLoss: 1000,
    maxPositionPercent: 10,
    enableStopLoss: true,
    enableTakeProfit: true,
    maxConcurrentTrades: 5,
    minLiquidity: 10000,
  });
  
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>({
    enableEmail: true,
    enableSMS: false,
    enableWebhook: false,
    profitThreshold: 100,
    lossThreshold: 50,
  });

  // 模拟数据
  useEffect(() => {
    const mockStrategies: StrategyConfig[] = [
      {
        id: '1',
        name: 'BTC套利策略',
        type: 'arbitrage',
        status: 'active',
        exchanges: ['binance', 'okx'],
        symbols: ['BTC/USDT'],
        minProfitPercent: 0.5,
        maxPositionSize: 10000,
        riskLevel: 'medium',
        autoExecute: true,
        stopLoss: 2,
        takeProfit: 5,
        maxDailyTrades: 10,
        cooldownPeriod: 300,
        createdAt: '2024-01-15T10:00:00Z',
        updatedAt: '2024-01-20T15:30:00Z',
        performance: {
          totalTrades: 156,
          successRate: 78.5,
          totalProfit: 2340.50,
          avgProfitPercent: 1.2,
          maxDrawdown: 5.8,
        },
      },
      {
        id: '2',
        name: 'ETH网格策略',
        type: 'grid',
        status: 'paused',
        exchanges: ['binance'],
        symbols: ['ETH/USDT'],
        minProfitPercent: 0.3,
        maxPositionSize: 5000,
        riskLevel: 'low',
        autoExecute: false,
        maxDailyTrades: 20,
        cooldownPeriod: 180,
        createdAt: '2024-01-10T08:00:00Z',
        updatedAt: '2024-01-18T12:00:00Z',
        performance: {
          totalTrades: 89,
          successRate: 85.2,
          totalProfit: 1120.30,
          avgProfitPercent: 0.8,
          maxDrawdown: 3.2,
        },
      },
    ];
    setStrategies(mockStrategies);
  }, []);

  const handleCreateStrategy = () => {
    setSelectedStrategy(null);
    form.resetFields();
    setIsModalVisible(true);
  };

  const handleEditStrategy = (strategy: StrategyConfig) => {
    setSelectedStrategy(strategy);
    form.setFieldsValue(strategy);
    setIsModalVisible(true);
  };

  const handleDeleteStrategy = (strategyId: string) => {
    setStrategies(prev => prev.filter(s => s.id !== strategyId));
    message.success('策略已删除');
  };

  const handleToggleStrategy = (strategyId: string) => {
    setStrategies(prev => prev.map(s => {
      if (s.id === strategyId) {
        const newStatus = s.status === 'active' ? 'paused' : 'active';
        return { ...s, status: newStatus };
      }
      return s;
    }));
  };

  const handleSaveStrategy = async (values: any) => {
    try {
      if (selectedStrategy) {
        // 更新策略
        setStrategies(prev => prev.map(s => 
          s.id === selectedStrategy.id 
            ? { ...s, ...values, updatedAt: new Date().toISOString() }
            : s
        ));
        message.success('策略已更新');
      } else {
        // 创建新策略
        const newStrategy: StrategyConfig = {
          ...values,
          id: Date.now().toString(),
          status: 'stopped',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        setStrategies(prev => [...prev, newStrategy]);
        message.success('策略已创建');
      }
      setIsModalVisible(false);
    } catch (error) {
      message.error('保存失败');
    }
  };

  const handleSaveRiskSettings = async (values: RiskSettings) => {
    try {
      setRiskSettings(values);
      message.success('风险设置已保存');
    } catch (error) {
      message.error('保存失败');
    }
  };

  const handleSaveNotificationSettings = async (values: NotificationSettings) => {
    try {
      setNotificationSettings(values);
      message.success('通知设置已保存');
    } catch (error) {
      message.error('保存失败');
    }
  };

  const strategyColumns = [
    {
      title: '策略名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: StrategyConfig) => (
        <Space>
          <Text strong>{name}</Text>
          <Tag color={record.type === 'arbitrage' ? 'blue' : record.type === 'grid' ? 'green' : 'orange'}>
            {record.type.toUpperCase()}
          </Tag>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colors = {
          active: 'success',
          paused: 'warning',
          stopped: 'default',
        };
        const icons = {
          active: <CheckCircleOutlined />,
          paused: <PauseCircleOutlined />,
          stopped: <WarningOutlined />,
        };
        return (
          <Tag color={colors[status as keyof typeof colors]} icon={icons[status as keyof typeof icons]}>
            {status.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: '交易所',
      dataIndex: 'exchanges',
      key: 'exchanges',
      render: (exchanges: string[]) => (
        <Space>
          {exchanges.map(exchange => (
            <Tag key={exchange} color="blue">{exchange.toUpperCase()}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '交易对',
      dataIndex: 'symbols',
      key: 'symbols',
      render: (symbols: string[]) => (
        <Space>
          {symbols.slice(0, 2).map(symbol => (
            <Tag key={symbol}>{symbol}</Tag>
          ))}
          {symbols.length > 2 && <Text>+{symbols.length - 2}</Text>}
        </Space>
      ),
    },
    {
      title: '最小利润率',
      dataIndex: 'minProfitPercent',
      key: 'minProfitPercent',
      render: (percent: number) => <Text>{percent}%</Text>,
    },
    {
      title: '风险等级',
      dataIndex: 'riskLevel',
      key: 'riskLevel',
      render: (level: string) => {
        const colors = {
          low: 'green',
          medium: 'orange',
          high: 'red',
        };
        return <Tag color={colors[level as keyof typeof colors]}>{level.toUpperCase()}</Tag>;
      },
    },
    {
      title: '绩效',
      key: 'performance',
      render: (record: StrategyConfig) => {
        if (!record.performance) return <Text>-</Text>;
        return (
          <Space direction="vertical" size="small">
            <Text>利润: ${record.performance.totalProfit.toFixed(2)}</Text>
            <Text>成功率: {record.performance.successRate.toFixed(1)}%</Text>
          </Space>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (record: StrategyConfig) => (
        <Space>
          <Tooltip title={record.status === 'active' ? '暂停' : '启动'}>
            <Button
              type="text"
              icon={record.status === 'active' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={() => handleToggleStrategy(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleEditStrategy(record)}
            />
          </Tooltip>
          <Tooltip title="详情">
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={() => {
                setSelectedStrategy(record);
                setIsDrawerVisible(true);
              }}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此策略？"
            onConfirm={() => handleDeleteStrategy(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const renderStrategyForm = () => (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSaveStrategy}
      initialValues={{
        type: 'arbitrage',
        riskLevel: 'medium',
        autoExecute: false,
        minProfitPercent: 0.5,
        maxPositionSize: 1000,
      }}
    >
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="name"
            label="策略名称"
            rules={[{ required: true, message: '请输入策略名称' }]}
          >
            <Input placeholder="输入策略名称" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="type"
            label="策略类型"
            rules={[{ required: true, message: '请选择策略类型' }]}
          >
            <Select>
              <Option value="arbitrage">套利策略</Option>
              <Option value="grid">网格策略</Option>
              <Option value="dca">定投策略</Option>
              <Option value="custom">自定义策略</Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="exchanges"
            label="交易所"
            rules={[{ required: true, message: '请选择交易所' }]}
          >
            <Select mode="multiple" placeholder="选择交易所">
              <Option value="binance">Binance</Option>
              <Option value="okx">OKX</Option>
              <Option value="huobi">Huobi</Option>
              <Option value="coinbase">Coinbase</Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="symbols"
            label="交易对"
            rules={[{ required: true, message: '请选择交易对' }]}
          >
            <Select mode="multiple" placeholder="选择交易对">
              <Option value="BTC/USDT">BTC/USDT</Option>
              <Option value="ETH/USDT">ETH/USDT</Option>
              <Option value="BNB/USDT">BNB/USDT</Option>
              <Option value="ADA/USDT">ADA/USDT</Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Form.Item
            name="minProfitPercent"
            label="最小利润率 (%)"
            rules={[{ required: true, message: '请输入最小利润率' }]}
          >
            <InputNumber
              min={0}
              max={100}
              step={0.1}
              style={{ width: '100%' }}
              placeholder="0.5"
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name="maxPositionSize"
            label="最大仓位 (USDT)"
            rules={[{ required: true, message: '请输入最大仓位' }]}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="1000"
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name="riskLevel"
            label="风险等级"
            rules={[{ required: true, message: '请选择风险等级' }]}
          >
            <Select>
              <Option value="low">低风险</Option>
              <Option value="medium">中风险</Option>
              <Option value="high">高风险</Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="stopLoss" label="止损 (%)">
            <InputNumber
              min={0}
              max={100}
              step={0.1}
              style={{ width: '100%' }}
              placeholder="2.0"
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="takeProfit" label="止盈 (%)">
            <InputNumber
              min={0}
              max={100}
              step={0.1}
              style={{ width: '100%' }}
              placeholder="5.0"
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="maxDailyTrades" label="每日最大交易次数">
            <InputNumber
              min={1}
              style={{ width: '100%' }}
              placeholder="10"
            />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="cooldownPeriod" label="冷却期 (秒)">
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="300"
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="autoExecute" label="自动执行" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
      </Row>
    </Form>
  );

  const renderRiskSettings = () => (
    <Form
      form={riskForm}
      layout="vertical"
      initialValues={riskSettings}
      onFinish={handleSaveRiskSettings}
    >
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="maxDailyLoss"
            label="每日最大亏损 (USDT)"
            rules={[{ required: true, message: '请输入每日最大亏损' }]}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="1000"
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="maxPositionPercent"
            label="最大仓位比例 (%)"
            rules={[{ required: true, message: '请输入最大仓位比例' }]}
          >
            <InputNumber
              min={0}
              max={100}
              style={{ width: '100%' }}
              placeholder="10"
            />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="enableStopLoss" label="启用止损" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="enableTakeProfit" label="启用止盈" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="maxConcurrentTrades"
            label="最大并发交易数"
            rules={[{ required: true, message: '请输入最大并发交易数' }]}
          >
            <InputNumber
              min={1}
              style={{ width: '100%' }}
              placeholder="5"
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="minLiquidity"
            label="最小流动性 (USDT)"
            rules={[{ required: true, message: '请输入最小流动性' }]}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="10000"
            />
          </Form.Item>
        </Col>
      </Row>

      <Form.Item>
        <Button type="primary" htmlType="submit">
          保存风险设置
        </Button>
      </Form.Item>
    </Form>
  );

  const renderNotificationSettings = () => (
    <Form
      form={notificationForm}
      layout="vertical"
      initialValues={notificationSettings}
      onFinish={handleSaveNotificationSettings}
    >
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="enableEmail" label="邮件通知" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="enableSMS" label="短信通知" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="enableWebhook" label="Webhook通知" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="profitThreshold"
            label="利润通知阈值 (USDT)"
            rules={[{ required: true, message: '请输入利润通知阈值' }]}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="100"
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="lossThreshold"
            label="亏损通知阈值 (USDT)"
            rules={[{ required: true, message: '请输入亏损通知阈值' }]}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder="50"
            />
          </Form.Item>
        </Col>
      </Row>

      <Form.Item
        name="webhookUrl"
        label="Webhook URL"
        rules={[
          { type: 'url', message: '请输入有效的URL' },
        ]}
      >
        <Input placeholder="https://your-webhook-url.com" />
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit">
          保存通知设置
        </Button>
      </Form.Item>
    </Form>
  );

  return (
    <div className="strategy-config-panel">
      <Card>
        <div className="panel-header">
          <Title level={3}>策略配置管理</Title>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateStrategy}
          >
            创建策略
          </Button>
        </div>

        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="策略列表" key="strategies">
            <Table
              columns={strategyColumns}
              dataSource={strategies}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              scroll={{ x: 1200 }}
            />
          </TabPane>
          
          <TabPane tab="风险设置" key="risk">
            <Card title="风险控制设置" size="small">
              {renderRiskSettings()}
            </Card>
          </TabPane>
          
          <TabPane tab="通知设置" key="notifications">
            <Card title="通知配置" size="small">
              {renderNotificationSettings()}
            </Card>
          </TabPane>
        </Tabs>
      </Card>

      {/* 策略编辑模态框 */}
      <Modal
        title={selectedStrategy ? '编辑策略' : '创建策略'}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setIsModalVisible(false)}>
            取消
          </Button>,
          <Button key="submit" type="primary" onClick={() => form.submit()}>
            保存
          </Button>,
        ]}
        width={800}
      >
        {renderStrategyForm()}
      </Modal>

      {/* 策略详情抽屉 */}
      <Drawer
        title="策略详情"
        placement="right"
        onClose={() => setIsDrawerVisible(false)}
        open={isDrawerVisible}
        width={600}
      >
        {selectedStrategy && (
          <div className="strategy-details">
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Card title="基本信息" size="small">
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic title="策略名称" value={selectedStrategy.name} />
                  </Col>
                  <Col span={12}>
                    <Statistic title="策略类型" value={selectedStrategy.type.toUpperCase()} />
                  </Col>
                </Row>
                <Divider />
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic title="最小利润率" value={selectedStrategy.minProfitPercent} suffix="%" />
                  </Col>
                  <Col span={12}>
                    <Statistic title="最大仓位" value={selectedStrategy.maxPositionSize} prefix="$" />
                  </Col>
                </Row>
              </Card>

              {selectedStrategy.performance && (
                <Card title="绩效统计" size="small">
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic
                        title="总利润"
                        value={selectedStrategy.performance.totalProfit}
                        precision={2}
                        prefix={<DollarOutlined />}
                        valueStyle={{ color: '#3f8600' }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title="成功率"
                        value={selectedStrategy.performance.successRate}
                        precision={1}
                        suffix="%"
                        prefix={<PercentageOutlined />}
                        valueStyle={{ color: '#1890ff' }}
                      />
                    </Col>
                  </Row>
                  <Divider />
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic
                        title="总交易次数"
                        value={selectedStrategy.performance.totalTrades}
                        prefix={<TrendingUpOutlined />}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title="最大回撤"
                        value={selectedStrategy.performance.maxDrawdown}
                        precision={1}
                        suffix="%"
                        valueStyle={{ color: '#cf1322' }}
                      />
                    </Col>
                  </Row>
                </Card>
              )}

              <Card title="配置详情" size="small">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <Text strong>交易所: </Text>
                    {selectedStrategy.exchanges.map(exchange => (
                      <Tag key={exchange} color="blue">{exchange.toUpperCase()}</Tag>
                    ))}
                  </div>
                  <div>
                    <Text strong>交易对: </Text>
                    {selectedStrategy.symbols.map(symbol => (
                      <Tag key={symbol}>{symbol}</Tag>
                    ))}
                  </div>
                  <div>
                    <Text strong>风险等级: </Text>
                    <Tag color={selectedStrategy.riskLevel === 'low' ? 'green' : selectedStrategy.riskLevel === 'medium' ? 'orange' : 'red'}>
                      {selectedStrategy.riskLevel.toUpperCase()}
                    </Tag>
                  </div>
                  <div>
                    <Text strong>自动执行: </Text>
                    <Tag color={selectedStrategy.autoExecute ? 'green' : 'red'}>
                      {selectedStrategy.autoExecute ? '启用' : '禁用'}
                    </Tag>
                  </div>
                </Space>
              </Card>
            </Space>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default StrategyConfigPanel;