import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

// Slices
import appSlice from './slices/appSlice';
import authSlice from './slices/authSlice';
import arbitrageSlice from './slices/arbitrageSlice';
import depositWithdrawSlice from './slices/depositWithdrawSlice';
import strategySlice from './slices/strategySlice';
import marketDataSlice from './slices/marketDataSlice';
import notificationSlice from './slices/notificationSlice';

// Middleware
import { createListenerMiddleware } from '@reduxjs/toolkit';

// Create listener middleware for side effects
const listenerMiddleware = createListenerMiddleware();

export const store = configureStore({
  reducer: {
    app: appSlice,
    auth: authSlice,
    arbitrage: arbitrageSlice,
    depositWithdraw: depositWithdrawSlice,
    strategy: strategySlice,
    marketData: marketDataSlice,
    notification: notificationSlice,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: [
          'persist/PERSIST',
          'persist/REHYDRATE',
          'persist/PAUSE',
          'persist/PURGE',
          'persist/REGISTER',
        ],
        ignoredPaths: ['register'],
      },
    }).prepend(listenerMiddleware.middleware),
  devTools: process.env.NODE_ENV !== 'production',
});

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

// Export typed hooks
export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

// Export listener middleware for use in slices
export { listenerMiddleware };

export default store;