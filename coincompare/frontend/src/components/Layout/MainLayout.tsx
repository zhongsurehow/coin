import React, { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Layout,
  Menu,
  Button,
  Avatar,
  Dropdown,
  Badge,
  Space,
  Typography,
  Tooltip,
  Switch,
  Divider,
  notification,
} from 'antd';
import {
  DashboardOutlined,
  SwapOutlined,
  BankOutlined,
  StrategyOutlined,
  LineChartOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  BellOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SunOutlined,
  MoonOutlined,
  WifiOutlined,
  DisconnectOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useAppSelector, useAppDispatch } from '../../hooks/redux';
import {
  toggleSidebar,
  toggleDarkMode,
  setConnectionStatus,
  addNotification,
  markAllNotificationsAsRead,
} from '../../store/slices/appSlice';
import { logout } from '../../store/slices/authSlice';
import { websocketService } from '../../services/websocketService';
import NotificationPanel from '../Common/NotificationPanel';
import ConnectionStatus from '../Common/ConnectionStatus';
import './MainLayout.css';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

interface MenuItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  path: string;
}

const menuItems: MenuItem[] = [
  {
    key: 'dashboard',
    icon: <DashboardOutlined />,
    label: '仪表板',
    path: '/dashboard',
  },
  {
    key: 'arbitrage',
    icon: <SwapOutlined />,
    label: '套利交易',
    path: '/arbitrage',
  },
  {
    key: 'deposit-withdraw',
    icon: <BankOutlined />,
    label: '充值提现',
    path: '/deposit-withdraw',
  },
  {
    key: 'strategy',
    icon: <StrategyOutlined />,
    label: '策略管理',
    path: '/strategy',
  },
  {
    key: 'market-data',
    icon: <LineChartOutlined />,
    label: '市场数据',
    path: '/market-data',
  },
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: '设置',
    path: '/settings',
  },
];

const MainLayout: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  
  const {
    sidebarCollapsed,
    isDarkMode,
    connectionStatus,
    notifications,
    serverStatus,
  } = useAppSelector(state => state.app);
  
  const { user } = useAppSelector(state => state.auth);
  
  const [notificationPanelVisible, setNotificationPanelVisible] = useState(false);
  
  // Get current menu key from location
  const currentMenuKey = location.pathname.split('/')[1] || 'dashboard';
  
  // Unread notifications count
  const unreadCount = notifications.filter(n => !n.read).length;
  
  useEffect(() => {
    // Initialize WebSocket connection
    const token = localStorage.getItem('authToken');
    if (token) {
      websocketService.connect(token);
      
      // Listen for connection status changes
      websocketService.onConnectionChange((status) => {
        dispatch(setConnectionStatus(status));
        
        if (status === 'connected') {
          dispatch(addNotification({
            type: 'success',
            title: '连接成功',
            message: '实时数据连接已建立',
            autoClose: true,
            duration: 3000,
          }));
        } else if (status === 'error') {
          dispatch(addNotification({
            type: 'error',
            title: '连接错误',
            message: '实时数据连接失败，请检查网络连接',
            autoClose: false,
          }));
        }
      });
      
      // Listen for real-time notifications
      websocketService.onNotification((notification) => {
        dispatch(addNotification(notification));
        
        // Show system notification if supported
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification(notification.title, {
            body: notification.message,
            icon: '/favicon.ico',
          });
        }
      });
    }
    
    return () => {
      websocketService.disconnect();
    };
  }, [dispatch]);
  
  // Request notification permission
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);
  
  const handleMenuClick = (key: string) => {
    const item = menuItems.find(item => item.key === key);
    if (item) {
      navigate(item.path);
    }
  };
  
  const handleLogout = () => {
    dispatch(logout());
    websocketService.disconnect();
    navigate('/login');
  };
  
  const handleNotificationClick = () => {
    setNotificationPanelVisible(true);
    if (unreadCount > 0) {
      dispatch(markAllNotificationsAsRead());
    }
  };
  
  // User dropdown menu
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
      onClick: () => navigate('/settings'),
    },
    {
      key: 'divider1',
      type: 'divider' as const,
    },
    {
      key: 'theme',
      icon: isDarkMode ? <SunOutlined /> : <MoonOutlined />,
      label: (
        <Space>
          <span>{isDarkMode ? '浅色模式' : '深色模式'}</span>
          <Switch
            size="small"
            checked={isDarkMode}
            onChange={() => dispatch(toggleDarkMode())}
            checkedChildren={<MoonOutlined />}
            unCheckedChildren={<SunOutlined />}
          />
        </Space>
      ),
    },
    {
      key: 'divider2',
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];
  
  return (
    <Layout className="main-layout">
      {/* Sidebar */}
      <Sider
        trigger={null}
        collapsible
        collapsed={sidebarCollapsed}
        width={240}
        className="main-sidebar"
        theme={isDarkMode ? 'dark' : 'light'}
      >
        {/* Logo */}
        <div className="sidebar-logo">
          <img src="/logo.svg" alt="CoinCompare" className="logo-image" />
          {!sidebarCollapsed && (
            <Text className="logo-text" strong>
              CoinCompare
            </Text>
          )}
        </div>
        
        {/* Navigation Menu */}
        <Menu
          mode="inline"
          selectedKeys={[currentMenuKey]}
          className="sidebar-menu"
          theme={isDarkMode ? 'dark' : 'light'}
          items={menuItems.map(item => ({
            key: item.key,
            icon: item.icon,
            label: item.label,
            onClick: () => handleMenuClick(item.key),
          }))}
        />
        
        {/* Connection Status */}
        {!sidebarCollapsed && (
          <div className="sidebar-footer">
            <ConnectionStatus status={connectionStatus} serverStatus={serverStatus} />
          </div>
        )}
      </Sider>
      
      {/* Main Content */}
      <Layout className="main-content-layout">
        {/* Header */}
        <Header className="main-header">
          <div className="header-left">
            <Button
              type="text"
              icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => dispatch(toggleSidebar())}
              className="sidebar-toggle"
            />
            
            {/* Connection Status Indicator */}
            <div className="connection-indicator">
              {connectionStatus === 'connected' ? (
                <Tooltip title="实时连接正常">
                  <WifiOutlined className="connection-icon connected" />
                </Tooltip>
              ) : connectionStatus === 'connecting' ? (
                <Tooltip title="正在连接...">
                  <WifiOutlined className="connection-icon connecting" />
                </Tooltip>
              ) : (
                <Tooltip title="连接断开">
                  <DisconnectOutlined className="connection-icon disconnected" />
                </Tooltip>
              )}
            </div>
            
            {/* Server Status */}
            {serverStatus !== 'online' && (
              <div className="server-status">
                <WarningOutlined className="warning-icon" />
                <Text type="warning">
                  {serverStatus === 'maintenance' ? '系统维护中' : '服务器离线'}
                </Text>
              </div>
            )}
          </div>
          
          <div className="header-right">
            <Space size="middle">
              {/* Theme Toggle */}
              <Tooltip title={isDarkMode ? '切换到浅色模式' : '切换到深色模式'}>
                <Button
                  type="text"
                  icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
                  onClick={() => dispatch(toggleDarkMode())}
                  className="theme-toggle"
                />
              </Tooltip>
              
              {/* Notifications */}
              <Tooltip title="通知">
                <Badge count={unreadCount} size="small">
                  <Button
                    type="text"
                    icon={<BellOutlined />}
                    onClick={handleNotificationClick}
                    className="notification-button"
                  />
                </Badge>
              </Tooltip>
              
              {/* User Menu */}
              <Dropdown
                menu={{ items: userMenuItems }}
                placement="bottomRight"
                trigger={['click']}
              >
                <Button type="text" className="user-button">
                  <Space>
                    <Avatar
                      size="small"
                      icon={<UserOutlined />}
                      src={user?.avatar}
                    />
                    <Text className="username">{user?.username || '用户'}</Text>
                  </Space>
                </Button>
              </Dropdown>
            </Space>
          </div>
        </Header>
        
        {/* Page Content */}
        <Content className="main-content">
          <div className="content-wrapper">
            <Outlet />
          </div>
        </Content>
      </Layout>
      
      {/* Notification Panel */}
      <NotificationPanel
        visible={notificationPanelVisible}
        onClose={() => setNotificationPanelVisible(false)}
        notifications={notifications}
      />
    </Layout>
  );
};

export default MainLayout;