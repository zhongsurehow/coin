import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { RootState } from '../index';
import { authService } from '../../services/authService';
import { websocketService } from '../../services/websocketService';

// Types
export interface AppState {
  isLoading: boolean;
  isAuthenticated: boolean;
  isDarkMode: boolean;
  sidebarCollapsed: boolean;
  connectionStatus: 'connected' | 'disconnected' | 'connecting' | 'error';
  lastActivity: number;
  notifications: Notification[];
  globalError: string | null;
  appVersion: string;
  serverStatus: 'online' | 'offline' | 'maintenance';
  userPreferences: UserPreferences;
}

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
  autoClose?: boolean;
  duration?: number;
}

export interface UserPreferences {
  language: string;
  timezone: string;
  currency: string;
  refreshInterval: number;
  soundEnabled: boolean;
  emailNotifications: boolean;
  pushNotifications: boolean;
  chartType: 'candlestick' | 'line' | 'area';
  defaultTimeframe: string;
}

const initialState: AppState = {
  isLoading: true,
  isAuthenticated: false,
  isDarkMode: localStorage.getItem('darkMode') === 'true',
  sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true',
  connectionStatus: 'disconnected',
  lastActivity: Date.now(),
  notifications: [],
  globalError: null,
  appVersion: '1.0.0',
  serverStatus: 'online',
  userPreferences: {
    language: 'en',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    currency: 'USD',
    refreshInterval: 5000,
    soundEnabled: true,
    emailNotifications: true,
    pushNotifications: true,
    chartType: 'candlestick',
    defaultTimeframe: '1h',
  },
};

// Async thunks
export const initializeApp = createAsyncThunk(
  'app/initialize',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      // Check if user is authenticated
      const token = localStorage.getItem('authToken');
      if (token) {
        try {
          const user = await authService.verifyToken(token);
          if (user) {
            dispatch(setAuthenticated(true));
            // Initialize WebSocket connection
            websocketService.connect(token);
          } else {
            localStorage.removeItem('authToken');
          }
        } catch (error) {
          localStorage.removeItem('authToken');
        }
      }

      // Load user preferences
      const savedPreferences = localStorage.getItem('userPreferences');
      if (savedPreferences) {
        dispatch(setUserPreferences(JSON.parse(savedPreferences)));
      }

      // Check server status
      await dispatch(checkServerStatus());

      return true;
    } catch (error) {
      return rejectWithValue('Failed to initialize application');
    }
  }
);

export const checkServerStatus = createAsyncThunk(
  'app/checkServerStatus',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch('/api/health');
      if (response.ok) {
        const data = await response.json();
        return data.status || 'online';
      } else {
        return 'offline';
      }
    } catch (error) {
      return 'offline';
    }
  }
);

export const updateUserActivity = createAsyncThunk(
  'app/updateActivity',
  async (_, { getState }) => {
    const state = getState() as RootState;
    const now = Date.now();
    const lastActivity = state.app.lastActivity;
    
    // If user has been inactive for more than 30 minutes, show warning
    if (now - lastActivity > 30 * 60 * 1000) {
      return { showInactivityWarning: true, timestamp: now };
    }
    
    return { showInactivityWarning: false, timestamp: now };
  }
);

// Slice
const appSlice = createSlice({
  name: 'app',
  initialState,
  reducers: {
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload;
    },
    
    setAuthenticated: (state, action: PayloadAction<boolean>) => {
      state.isAuthenticated = action.payload;
      if (!action.payload) {
        // Clear sensitive data when logging out
        state.notifications = [];
        websocketService.disconnect();
      }
    },
    
    toggleDarkMode: (state) => {
      state.isDarkMode = !state.isDarkMode;
      localStorage.setItem('darkMode', state.isDarkMode.toString());
    },
    
    setDarkMode: (state, action: PayloadAction<boolean>) => {
      state.isDarkMode = action.payload;
      localStorage.setItem('darkMode', action.payload.toString());
    },
    
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
      localStorage.setItem('sidebarCollapsed', state.sidebarCollapsed.toString());
    },
    
    setSidebarCollapsed: (state, action: PayloadAction<boolean>) => {
      state.sidebarCollapsed = action.payload;
      localStorage.setItem('sidebarCollapsed', action.payload.toString());
    },
    
    setConnectionStatus: (state, action: PayloadAction<AppState['connectionStatus']>) => {
      state.connectionStatus = action.payload;
    },
    
    addNotification: (state, action: PayloadAction<Omit<Notification, 'id' | 'timestamp' | 'read'>>) => {
      const notification: Notification = {
        ...action.payload,
        id: `notification_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: Date.now(),
        read: false,
      };
      
      state.notifications.unshift(notification);
      
      // Keep only last 50 notifications
      if (state.notifications.length > 50) {
        state.notifications = state.notifications.slice(0, 50);
      }
    },
    
    markNotificationAsRead: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(n => n.id === action.payload);
      if (notification) {
        notification.read = true;
      }
    },
    
    markAllNotificationsAsRead: (state) => {
      state.notifications.forEach(notification => {
        notification.read = true;
      });
    },
    
    removeNotification: (state, action: PayloadAction<string>) => {
      state.notifications = state.notifications.filter(n => n.id !== action.payload);
    },
    
    clearNotifications: (state) => {
      state.notifications = [];
    },
    
    setGlobalError: (state, action: PayloadAction<string | null>) => {
      state.globalError = action.payload;
    },
    
    clearGlobalError: (state) => {
      state.globalError = null;
    },
    
    setUserPreferences: (state, action: PayloadAction<Partial<UserPreferences>>) => {
      state.userPreferences = { ...state.userPreferences, ...action.payload };
      localStorage.setItem('userPreferences', JSON.stringify(state.userPreferences));
    },
    
    updateLastActivity: (state) => {
      state.lastActivity = Date.now();
    },
    
    setServerStatus: (state, action: PayloadAction<AppState['serverStatus']>) => {
      state.serverStatus = action.payload;
    },
  },
  
  extraReducers: (builder) => {
    builder
      // Initialize app
      .addCase(initializeApp.pending, (state) => {
        state.isLoading = true;
        state.globalError = null;
      })
      .addCase(initializeApp.fulfilled, (state) => {
        state.isLoading = false;
      })
      .addCase(initializeApp.rejected, (state, action) => {
        state.isLoading = false;
        state.globalError = action.payload as string;
      })
      
      // Check server status
      .addCase(checkServerStatus.fulfilled, (state, action) => {
        state.serverStatus = action.payload;
      })
      .addCase(checkServerStatus.rejected, (state) => {
        state.serverStatus = 'offline';
      })
      
      // Update user activity
      .addCase(updateUserActivity.fulfilled, (state, action) => {
        state.lastActivity = action.payload.timestamp;
        if (action.payload.showInactivityWarning) {
          // Add inactivity warning notification
          const notification: Notification = {
            id: `inactivity_${Date.now()}`,
            type: 'warning',
            title: 'Inactivity Warning',
            message: 'You have been inactive for a while. Your session may expire soon.',
            timestamp: Date.now(),
            read: false,
            autoClose: false,
          };
          state.notifications.unshift(notification);
        }
      });
  },
});

// Actions
export const {
  setLoading,
  setAuthenticated,
  toggleDarkMode,
  setDarkMode,
  toggleSidebar,
  setSidebarCollapsed,
  setConnectionStatus,
  addNotification,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  removeNotification,
  clearNotifications,
  setGlobalError,
  clearGlobalError,
  setUserPreferences,
  updateLastActivity,
  setServerStatus,
} = appSlice.actions;

// Selectors
export const selectApp = (state: RootState) => state.app;
export const selectIsAuthenticated = (state: RootState) => state.app.isAuthenticated;
export const selectIsDarkMode = (state: RootState) => state.app.isDarkMode;
export const selectSidebarCollapsed = (state: RootState) => state.app.sidebarCollapsed;
export const selectConnectionStatus = (state: RootState) => state.app.connectionStatus;
export const selectNotifications = (state: RootState) => state.app.notifications;
export const selectUnreadNotifications = (state: RootState) => 
  state.app.notifications.filter(n => !n.read);
export const selectGlobalError = (state: RootState) => state.app.globalError;
export const selectUserPreferences = (state: RootState) => state.app.userPreferences;
export const selectServerStatus = (state: RootState) => state.app.serverStatus;

export default appSlice.reducer;