import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import { Provider } from 'react-redux';
import { store } from './store';
import { useAppSelector, useAppDispatch } from './hooks/redux';
import { initializeApp } from './store/slices/appSlice';

// Layout Components
import MainLayout from './components/Layout/MainLayout';
import AuthLayout from './components/Layout/AuthLayout';

// Page Components
import Dashboard from './pages/Dashboard';
import ArbitragePage from './pages/Arbitrage';
import DepositWithdrawPage from './pages/DepositWithdraw';
import StrategyPage from './pages/Strategy';
import MarketDataPage from './pages/MarketData';
import SettingsPage from './pages/Settings';
import LoginPage from './pages/Auth/Login';
import RegisterPage from './pages/Auth/Register';

// Styles
import 'antd/dist/reset.css';

const AppContent: React.FC = () => {
  const dispatch = useAppDispatch();
  const { isAuthenticated, isDarkMode, isLoading } = useAppSelector(state => state.app);

  useEffect(() => {
    dispatch(initializeApp());
  }, [dispatch]);

  if (isLoading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <p>Loading CoinCompare...</p>
      </div>
    );
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1890ff',
          borderRadius: 8,
          colorBgContainer: isDarkMode ? '#141414' : '#ffffff',
        },
      }}
    >
      <Router>
        <div className={`app ${isDarkMode ? 'dark-theme' : 'light-theme'}`}>
          <Routes>
            {/* Public Routes */}
            <Route path="/login" element={
              !isAuthenticated ? (
                <AuthLayout>
                  <LoginPage />
                </AuthLayout>
              ) : (
                <Navigate to="/dashboard" replace />
              )
            } />
            <Route path="/register" element={
              !isAuthenticated ? (
                <AuthLayout>
                  <RegisterPage />
                </AuthLayout>
              ) : (
                <Navigate to="/dashboard" replace />
              )
            } />

            {/* Protected Routes */}
            <Route path="/" element={
              isAuthenticated ? (
                <MainLayout />
              ) : (
                <Navigate to="/login" replace />
              )
            }>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="arbitrage" element={<ArbitragePage />} />
              <Route path="deposit-withdraw" element={<DepositWithdrawPage />} />
              <Route path="strategy" element={<StrategyPage />} />
              <Route path="market-data" element={<MarketDataPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>

            {/* Fallback Route */}
            <Route path="*" element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <Navigate to="/login" replace />
              )
            } />
          </Routes>
        </div>
      </Router>
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  return (
    <Provider store={store}>
      <AppContent />
    </Provider>
  );
};

export default App;
