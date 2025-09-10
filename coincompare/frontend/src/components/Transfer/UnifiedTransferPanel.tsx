import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Space,
  Typography,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Progress,
  Alert,
  Modal,
  Steps,
  Tooltip,
  Switch,
  InputNumber,
  Divider,
  Timeline,
  Badge,
  message
} from 'antd';
import {
  SwapOutlined,
  SendOutlined,
  ReceiptOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  CalculatorOutlined,
  ThunderboltOutlined,
  SafetyOutlined
} from '@ant-design/icons';
import './UnifiedTransferPanel.css';

const { Title, Text } = Typography;
const { Option } = Select;
const { Step } = Steps;

interface Exchange {
  id: string;
  name: string;
  balance: number;
  available: number;
  frozen: number;
  status: 'online' | 'offline' | 'maintenance';
}

interface TransferRoute {
  id: string;
  fromExchange: string;
  toExchange: string;
  method: 'direct' | 'bridge' | 'multi_hop';
  estimatedTime: number;
  fee: number;
  feePercent: number;
  minAmount: number;
  maxAmount: number;
  reliability: number;
  steps: string[];
}

interface TransferRecord {
  id: string;
  fromExchange: string;
  toExchange: string;
  amount: number;
  currency: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  fee: number;
  estimatedTime: number;
  actualTime?: number;
  createdAt: string;
  completedAt?: string;
  txHash?: string;
  route: TransferRoute;
}

const UnifiedTransferPanel: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [routes, setRoutes] = useState<TransferRoute[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<TransferRoute | null>(null);
  const [transferHistory, setTransferHistory] = useState<TransferRecord[]>([]);
  const [showRouteModal, setShowRouteModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [autoOptimize, setAutoOptimize] = useState(true);
  const [riskLevel, setRiskLevel] = useState<'low' | 'medium' | 'high'>('medium');

  // 模拟数据初始化
  useEffect(() => {
    initializeData();
  }, []);

  const initializeData = () => {
    // 模拟交易所数据
    const mockExchanges: Exchange[] = [
      {
        id: 'binance',
        name: 'Binance',
        balance: 15420.50,
        available: 14200.30,
        frozen: 1220.20,
        status: 'online'
      },
      {
        id: 'okx',
        name: 'OKX',
        balance: 8750.80,
        available: 8500.60,
        frozen: 250.20,
        status: 'online'
      },
      {
        id: 'huobi',
        name: 'Huobi',
        balance: 5230.40,
        available: 5000.00,
        frozen: 230.40,
        status: 'maintenance'
      },
      {
        id: 'gate',
        name: 'Gate.io',
        balance: 3450.20,
        available: 3400.00,
        frozen: 50.20,
        status: 'online'
      }
    ];

    // 模拟转账历史
    const mockHistory: TransferRecord[] = [
      {
        id: 'tx_001',
        fromExchange: 'binance',
        toExchange: 'okx',
        amount: 1000,
        currency: 'USDT',
        status: 'completed',
        fee: 1.5,
        estimatedTime: 300,
        actualTime: 280,
        createdAt: '2024-01-15 14:30:00',
        completedAt: '2024-01-15 14:34:40',
        txHash: '0x1234...abcd',
        route: {
          id: 'route_001',
          fromExchange: 'binance',
          toExchange: 'okx',
          method: 'direct',
          estimatedTime: 300,
          fee: 1.5,
          feePercent: 0.15,
          minAmount: 10,
          maxAmount: 50000,
          reliability: 98.5,
          steps: ['提取到钱包', '转账到目标交易所', '确认到账']
        }
      },
      {
        id: 'tx_002',
        fromExchange: 'okx',
        toExchange: 'gate',
        amount: 500,
        currency: 'USDT',
        status: 'processing',
        fee: 2.0,
        estimatedTime: 600,
        createdAt: '2024-01-15 15:00:00',
        route: {
          id: 'route_002',
          fromExchange: 'okx',
          toExchange: 'gate',
          method: 'bridge',
          estimatedTime: 600,
          fee: 2.0,
          feePercent: 0.4,
          minAmount: 50,
          maxAmount: 10000,
          reliability: 95.2,
          steps: ['提取到中继桥', '跨链转账', '确认到账']
        }
      }
    ];

    setExchanges(mockExchanges);
    setTransferHistory(mockHistory);
  };

  const calculateRoutes = async (fromExchange: string, toExchange: string, amount: number) => {
    if (!fromExchange || !toExchange || !amount) return;
    
    setCalculating(true);
    
    // 模拟路径计算
    setTimeout(() => {
      const mockRoutes: TransferRoute[] = [
        {
          id: 'route_direct',
          fromExchange,
          toExchange,
          method: 'direct',
          estimatedTime: 300,
          fee: amount * 0.001,
          feePercent: 0.1,
          minAmount: 10,
          maxAmount: 50000,
          reliability: 98.5,
          steps: ['提取到钱包', '转账到目标交易所', '确认到账']
        },
        {
          id: 'route_bridge',
          fromExchange,
          toExchange,
          method: 'bridge',
          estimatedTime: 600,
          fee: amount * 0.002,
          feePercent: 0.2,
          minAmount: 50,
          maxAmount: 20000,
          reliability: 95.2,
          steps: ['提取到中继桥', '跨链转账', '确认到账']
        },
        {
          id: 'route_multi',
          fromExchange,
          toExchange,
          method: 'multi_hop',
          estimatedTime: 900,
          fee: amount * 0.0015,
          feePercent: 0.15,
          minAmount: 100,
          maxAmount: 30000,
          reliability: 92.8,
          steps: ['提取到中转交易所', '内部转账', '提取到目标交易所', '确认到账']
        }
      ];
      
      setRoutes(mockRoutes);
      if (autoOptimize) {
        // 自动选择最优路径（综合考虑费用、时间、可靠性）
        const bestRoute = mockRoutes.reduce((best, current) => {
          const bestScore = best.reliability * 0.4 + (1 - best.feePercent) * 0.3 + (1 - best.estimatedTime / 3600) * 0.3;
          const currentScore = current.reliability * 0.4 + (1 - current.feePercent) * 0.3 + (1 - current.estimatedTime / 3600) * 0.3;
          return currentScore > bestScore ? current : best;
        });
        setSelectedRoute(bestRoute);
      }
      setCalculating(false);
    }, 1500);
  };

  const handleSubmit = async (values: any) => {
    if (!selectedRoute) {
      message.error('请选择转账路径');
      return;
    }

    setLoading(true);
    
    try {
      // 模拟转账提交
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      message.success('转账请求已提交，正在处理中...');
      form.resetFields();
      setRoutes([]);
      setSelectedRoute(null);
      
      // 刷新历史记录
      // 这里应该调用实际的API
      
    } catch (error) {
      message.error('转账提交失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const getExchangeStatus = (status: string) => {
    const statusMap = {
      online: { color: 'green', text: '在线' },
      offline: { color: 'red', text: '离线' },
      maintenance: { color: 'orange', text: '维护中' }
    };
    return statusMap[status as keyof typeof statusMap] || { color: 'gray', text: '未知' };
  };

  const getRouteMethodText = (method: string) => {
    const methodMap = {
      direct: '直接转账',
      bridge: '跨链桥',
      multi_hop: '多跳转账'
    };
    return methodMap[method as keyof typeof methodMap] || method;
  };

  const getStatusColor = (status: string) => {
    const colorMap = {
      pending: 'orange',
      processing: 'blue',
      completed: 'green',
      failed: 'red',
      cancelled: 'gray'
    };
    return colorMap[status as keyof typeof colorMap] || 'gray';
  };

  const routeColumns = [
    {
      title: '路径类型',
      dataIndex: 'method',
      key: 'method',
      render: (method: string) => (
        <Tag color={method === 'direct' ? 'green' : method === 'bridge' ? 'blue' : 'orange'}>
          {getRouteMethodText(method)}
        </Tag>
      )
    },
    {
      title: '预计时间',
      dataIndex: 'estimatedTime',
      key: 'estimatedTime',
      render: (time: number) => `${Math.floor(time / 60)}分${time % 60}秒`
    },
    {
      title: '手续费',
      dataIndex: 'fee',
      key: 'fee',
      render: (fee: number, record: TransferRoute) => (
        <Space direction="vertical" size={0}>
          <Text>{fee.toFixed(4)} USDT</Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {record.feePercent.toFixed(2)}%
          </Text>
        </Space>
      )
    },
    {
      title: '可靠性',
      dataIndex: 'reliability',
      key: 'reliability',
      render: (reliability: number) => (
        <Progress
          percent={reliability}
          size="small"
          format={(percent) => `${percent}%`}
          strokeColor={reliability >= 95 ? '#52c41a' : reliability >= 90 ? '#faad14' : '#ff4d4f'}
        />
      )
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record: TransferRoute) => (
        <Button
          type={selectedRoute?.id === record.id ? 'primary' : 'default'}
          size="small"
          onClick={() => setSelectedRoute(record)}
        >
          {selectedRoute?.id === record.id ? '已选择' : '选择'}
        </Button>
      )
    }
  ];

  const historyColumns = [
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 150
    },
    {
      title: '路径',
      key: 'route',
      render: (_, record: TransferRecord) => (
        <Space>
          <Text>{record.fromExchange}</Text>
          <SwapOutlined />
          <Text>{record.toExchange}</Text>
        </Space>
      )
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number, record: TransferRecord) => (
        `${amount} ${record.currency}`
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Badge
          status={getStatusColor(status) as any}
          text={status === 'pending' ? '待处理' : 
                status === 'processing' ? '处理中' : 
                status === 'completed' ? '已完成' : 
                status === 'failed' ? '失败' : '已取消'}
        />
      )
    },
    {
      title: '手续费',
      dataIndex: 'fee',
      key: 'fee',
      render: (fee: number) => `${fee} USDT`
    }
  ];

  return (
    <div className="unified-transfer-panel">
      <Card className="transfer-header">
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={3}>
              <SwapOutlined /> 统一转账
            </Title>
            <Text type="secondary">跨交易所资金调度，智能路径优化</Text>
          </Col>
          <Col>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => window.location.reload()}
              >
                刷新
              </Button>
              <Button
                icon={<ClockCircleOutlined />}
                onClick={() => setShowHistoryModal(true)}
              >
                转账历史
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]}>
        {/* 左侧：转账表单 */}
        <Col xs={24} lg={14}>
          <Card title="转账配置" className="transfer-form-card">
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSubmit}
              onValuesChange={(changedValues, allValues) => {
                if (changedValues.fromExchange || changedValues.toExchange || changedValues.amount) {
                  calculateRoutes(allValues.fromExchange, allValues.toExchange, allValues.amount);
                }
              }}
            >
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    label="源交易所"
                    name="fromExchange"
                    rules={[{ required: true, message: '请选择源交易所' }]}
                  >
                    <Select placeholder="选择源交易所">
                      {exchanges.map(exchange => {
                        const status = getExchangeStatus(exchange.status);
                        return (
                          <Option
                            key={exchange.id}
                            value={exchange.id}
                            disabled={exchange.status !== 'online'}
                          >
                            <Space>
                              <Badge status={status.color as any} />
                              {exchange.name}
                              <Text type="secondary">
                                ({exchange.available.toFixed(2)} USDT)
                              </Text>
                            </Space>
                          </Option>
                        );
                      })}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    label="目标交易所"
                    name="toExchange"
                    rules={[{ required: true, message: '请选择目标交易所' }]}
                  >
                    <Select placeholder="选择目标交易所">
                      {exchanges.map(exchange => {
                        const status = getExchangeStatus(exchange.status);
                        return (
                          <Option
                            key={exchange.id}
                            value={exchange.id}
                            disabled={exchange.status !== 'online'}
                          >
                            <Space>
                              <Badge status={status.color as any} />
                              {exchange.name}
                            </Space>
                          </Option>
                        );
                      })}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    label="转账金额"
                    name="amount"
                    rules={[{ required: true, message: '请输入转账金额' }]}
                  >
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder="输入金额"
                      min={0}
                      precision={2}
                      addonAfter="USDT"
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="风险等级">
                    <Select
                      value={riskLevel}
                      onChange={setRiskLevel}
                    >
                      <Option value="low">
                        <Space>
                          <SafetyOutlined style={{ color: '#52c41a' }} />
                          低风险
                        </Space>
                      </Option>
                      <Option value="medium">
                        <Space>
                          <ExclamationCircleOutlined style={{ color: '#faad14' }} />
                          中风险
                        </Space>
                      </Option>
                      <Option value="high">
                        <Space>
                          <ThunderboltOutlined style={{ color: '#ff4d4f' }} />
                          高风险
                        </Space>
                      </Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item>
                <Space>
                  <Switch
                    checked={autoOptimize}
                    onChange={setAutoOptimize}
                    checkedChildren="自动优化"
                    unCheckedChildren="手动选择"
                  />
                  <Tooltip title="自动选择最优转账路径">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              </Form.Item>

              {/* 路径选择 */}
              {routes.length > 0 && (
                <Card
                  title={
                    <Space>
                      <CalculatorOutlined />
                      可用路径
                      {calculating && <Text type="secondary">(计算中...)</Text>}
                    </Space>
                  }
                  size="small"
                  className="routes-card"
                >
                  <Table
                    dataSource={routes}
                    columns={routeColumns}
                    pagination={false}
                    size="small"
                    rowKey="id"
                    loading={calculating}
                    rowSelection={{
                      type: 'radio',
                      selectedRowKeys: selectedRoute ? [selectedRoute.id] : [],
                      onSelect: (record) => setSelectedRoute(record)
                    }}
                  />
                  
                  {selectedRoute && (
                    <Alert
                      message="选中路径详情"
                      description={
                        <Timeline size="small">
                          {selectedRoute.steps.map((step, index) => (
                            <Timeline.Item key={index}>
                              {step}
                            </Timeline.Item>
                          ))}
                        </Timeline>
                      }
                      type="info"
                      style={{ marginTop: 16 }}
                    />
                  )}
                </Card>
              )}

              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  disabled={!selectedRoute}
                  size="large"
                  icon={<SendOutlined />}
                  block
                >
                  提交转账
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>

        {/* 右侧：账户余额 */}
        <Col xs={24} lg={10}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card title="账户余额" className="balance-card">
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                {exchanges.map(exchange => {
                  const status = getExchangeStatus(exchange.status);
                  return (
                    <Card key={exchange.id} size="small" className="exchange-balance">
                      <Row justify="space-between" align="middle">
                        <Col>
                          <Space>
                            <Badge status={status.color as any} />
                            <Text strong>{exchange.name}</Text>
                            <Tag color={status.color}>{status.text}</Tag>
                          </Space>
                        </Col>
                        <Col>
                          <Space direction="vertical" size={0} style={{ textAlign: 'right' }}>
                            <Text strong>{exchange.balance.toFixed(2)} USDT</Text>
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                              可用: {exchange.available.toFixed(2)}
                            </Text>
                          </Space>
                        </Col>
                      </Row>
                    </Card>
                  );
                })}
              </Space>
            </Card>

            <Card title="转账统计" className="stats-card">
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="今日转账"
                    value={5}
                    suffix="笔"
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="总金额"
                    value={12500}
                    suffix="USDT"
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Col>
              </Row>
              <Divider />
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="成功率"
                    value={98.5}
                    suffix="%"
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="平均时间"
                    value={4.2}
                    suffix="分钟"
                    valueStyle={{ color: '#722ed1' }}
                  />
                </Col>
              </Row>
            </Card>
          </Space>
        </Col>
      </Row>

      {/* 转账历史模态框 */}
      <Modal
        title="转账历史"
        open={showHistoryModal}
        onCancel={() => setShowHistoryModal(false)}
        footer={null}
        width={800}
      >
        <Table
          dataSource={transferHistory}
          columns={historyColumns}
          pagination={{ pageSize: 10 }}
          size="small"
          rowKey="id"
        />
      </Modal>
    </div>
  );
};

export default UnifiedTransferPanel;