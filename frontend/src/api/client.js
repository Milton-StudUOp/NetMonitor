import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getAuthToken = () => sessionStorage.getItem('netmonitor.auth.token');
export const setAuthToken = (token) => token ? sessionStorage.setItem('netmonitor.auth.token', token) : sessionStorage.removeItem('netmonitor.auth.token');

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && getAuthToken()) {
    setAuthToken(null);
    window.dispatchEvent(new Event('netmonitor:session-expired'));
  }
  return Promise.reject(error);
});

export default api;
