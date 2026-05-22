import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api`;

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth API
export const authApi = {
  register: async (email, password, role = 'USER') => {
    const response = await api.post('/auth/register', { email, password, role });
    return response.data;
  },
  login: async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
  },
  getMe: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
  logout: async () => {
    const response = await api.post('/auth/logout');
    return response.data;
  },
};

// Ramp API (for users)
export const rampApi = {
  getPrices: async () => {
    const response = await api.get('/ramp/prices');
    return response.data;
  },
  
  // ========================
  // PoR-Powered On-Ramp (Fiat → Crypto)
  // ========================
  createOnrampQuote: async (fiatAmount, cryptoCurrency, walletAddress = null) => {
    const response = await api.post('/ramp/onramp/por/quote', {
      fiat_amount: fiatAmount,
      crypto_currency: cryptoCurrency,
      wallet_address: walletAddress,
    });
    return response.data;
  },
  executeOnramp: async (quoteId, walletAddress) => {
    const response = await api.post('/ramp/onramp/por/execute', {
      quote_id: quoteId,
      wallet_address: walletAddress,
    });
    return response.data;
  },
  processOnrampPayment: async (quoteId, paymentRef, amountPaid) => {
    const response = await api.post('/ramp/onramp/por/payment/process', {
      quote_id: quoteId,
      payment_ref: paymentRef,
      amount_paid: amountPaid,
    });
    return response.data;
  },
  getOnrampTransaction: async (quoteId) => {
    const response = await api.get(`/ramp/onramp/por/transaction/${quoteId}`);
    return response.data;
  },
  getOnrampTimeline: async (quoteId) => {
    const response = await api.get(`/ramp/onramp/por/transaction/${quoteId}/timeline`);
    return response.data;
  },
  
  // ========================
  // PoR-Powered Off-Ramp (Crypto → Fiat)
  // ========================
  createOfframpQuote: async (cryptoAmount, cryptoCurrency, bankAccount = null) => {
    const response = await api.post('/ramp/offramp/quote', {
      crypto_amount: cryptoAmount,
      crypto_currency: cryptoCurrency,
      bank_account: bankAccount,
    });
    return response.data;
  },
  executeOfframp: async (quoteId, bankAccount) => {
    const response = await api.post('/ramp/offramp/execute', {
      quote_id: quoteId,
      bank_account: bankAccount,
    });
    return response.data;
  },
  processOfframpDeposit: async (quoteId, txHash, amount) => {
    const response = await api.post('/ramp/offramp/deposit/process', {
      quote_id: quoteId,
      tx_hash: txHash,
      amount: amount,
    });
    return response.data;
  },
  getOfframpTransaction: async (quoteId) => {
    const response = await api.get(`/ramp/offramp/transaction/${quoteId}`);
    return response.data;
  },
  getOfframpTimeline: async (quoteId) => {
    const response = await api.get(`/ramp/offramp/transaction/${quoteId}/timeline`);
    return response.data;
  },
  
  // ========================
  // General
  // ========================
  getTransactions: async () => {
    const response = await api.get('/ramp/transactions');
    return response.data;
  },
  getTransaction: async (quoteId) => {
    // Try on-ramp first, then off-ramp
    try {
      const response = await api.get(`/ramp/onramp/por/transaction/${quoteId}`);
      return response.data;
    } catch (e) {
      const response = await api.get(`/ramp/offramp/transaction/${quoteId}`);
      return response.data;
    }
  },
};

// Developer API
export const devApi = {
  getApiKeys: async () => {
    const response = await api.get('/dev/api-keys');
    return response.data;
  },
  createApiKey: async (name, description = '', rateLimit = 1000) => {
    const response = await api.post('/dev/api-keys', {
      name,
      description,
      rate_limit: rateLimit,
    });
    return response.data;
  },
  revokeApiKey: async (keyId) => {
    const response = await api.delete(`/dev/api-keys/${keyId}`);
    return response.data;
  },
  getDashboard: async () => {
    const response = await api.get('/dev/dashboard');
    return response.data;
  },
};

// Health check
export const healthApi = {
  check: async () => {
    const response = await api.get('/health');
    return response.data;
  },
  rampHealth: async () => {
    const response = await api.get('/ramp-api-health');
    return response.data;
  },
};

export default api;
