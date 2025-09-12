// Placeholder for authService.ts
export const authService = {
  login: async () => {
    console.log('authService.login called');
    return { user: { name: 'testuser' }, token: 'testtoken' };
  },
  logout: async () => {
    console.log('authService.logout called');
  },
  register: async () => {
    console.log('authService.register called');
    return { user: { name: 'testuser' }, token: 'testtoken' };
  },
};
