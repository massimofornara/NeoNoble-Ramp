import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { devApi } from '../api';
import {
  Coins, Key, Plus, Trash2, Copy, Eye, EyeOff, Shield,
  LogOut, AlertCircle, CheckCircle, Loader2, Activity,
  Code, BookOpen, ChevronRight
} from 'lucide-react';

export default function DevPortal() {
  const { user, logout, isAuthenticated, isDeveloper } = useAuth();
  const navigate = useNavigate();
  
  const [apiKeys, setApiKeys] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  
  // New key form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyDescription, setNewKeyDescription] = useState('');
  const [newKeyRateLimit, setNewKeyRateLimit] = useState(1000);
  
  // Created key display
  const [createdKey, setCreatedKey] = useState(null);
  const [showSecret, setShowSecret] = useState(false);
  const [copiedField, setCopiedField] = useState('');
  
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/dev/login');
      return;
    }
    if (!isDeveloper) {
      navigate('/dashboard');
      return;
    }
    loadData();
  }, [isAuthenticated, isDeveloper, navigate]);

  const loadData = async () => {
    try {
      const dashboard = await devApi.getDashboard();
      setApiKeys(dashboard.keys || []);
      setStats({
        totalKeys: dashboard.total_keys,
        activeKeys: dashboard.active_keys,
        totalApiCalls: dashboard.total_api_calls
      });
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError('Failed to load API keys');
    } finally {
      setLoading(false);
    }
  };

  const createApiKey = async (e) => {
    e.preventDefault();
    setError('');
    setCreating(true);

    try {
      const key = await devApi.createApiKey(newKeyName, newKeyDescription, newKeyRateLimit);
      setCreatedKey(key);
      setShowCreateForm(false);
      setNewKeyName('');
      setNewKeyDescription('');
      setNewKeyRateLimit(1000);
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const revokeKey = async (keyId) => {
    if (!window.confirm('Are you sure you want to revoke this API key? This action cannot be undone.')) {
      return;
    }

    try {
      await devApi.revokeApiKey(keyId);
      setSuccess('API key revoked successfully');
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to revoke API key');
    }
  };

  const copyToClipboard = (text, field) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(''), 2000);
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  if (!isAuthenticated || !isDeveloper) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Header */}
      <header className="border-b border-white/10 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center space-x-2">
              <Coins className="h-8 w-8 text-purple-400" />
              <span className="text-xl font-bold text-white">NeoNoble</span>
              <span className="bg-purple-600 text-white text-xs px-2 py-1 rounded">Dev Portal</span>
            </Link>
            <div className="flex items-center space-x-4">
              <Link to="/dashboard" className="text-gray-300 hover:text-white px-3 py-2 text-sm">
                User Dashboard
              </Link>
              <span className="text-gray-400 text-sm">{user?.email}</span>
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-white p-2"
                data-testid="logout-btn"
              >
                <LogOut className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6">
              <div className="flex items-center space-x-3">
                <div className="bg-purple-500/20 p-3 rounded-lg">
                  <Key className="h-6 w-6 text-purple-400" />
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Total API Keys</p>
                  <p className="text-2xl font-bold text-white">{stats.totalKeys}</p>
                </div>
              </div>
            </div>
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6">
              <div className="flex items-center space-x-3">
                <div className="bg-green-500/20 p-3 rounded-lg">
                  <Shield className="h-6 w-6 text-green-400" />
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Active Keys</p>
                  <p className="text-2xl font-bold text-white">{stats.activeKeys}</p>
                </div>
              </div>
            </div>
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6">
              <div className="flex items-center space-x-3">
                <div className="bg-blue-500/20 p-3 rounded-lg">
                  <Activity className="h-6 w-6 text-blue-400" />
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Total API Calls</p>
                  <p className="text-2xl font-bold text-white">{stats.totalApiCalls.toLocaleString()}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center space-x-2 text-red-200">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <span>{error}</span>
            <button onClick={() => setError('')} className="ml-auto">×</button>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-green-500/20 border border-green-500/50 rounded-lg flex items-center space-x-2 text-green-200">
            <CheckCircle className="h-5 w-5 flex-shrink-0" />
            <span>{success}</span>
            <button onClick={() => setSuccess('')} className="ml-auto">×</button>
          </div>
        )}

        {/* Created Key Modal */}
        {createdKey && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-slate-800 rounded-2xl p-6 max-w-lg w-full" data-testid="created-key-modal">
              <div className="flex items-center space-x-3 mb-6">
                <div className="bg-green-500/20 p-3 rounded-full">
                  <CheckCircle className="h-8 w-8 text-green-400" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-white">API Key Created!</h3>
                  <p className="text-gray-400 text-sm">Save your secret now - it will not be shown again</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">API Key</label>
                  <div className="flex items-center space-x-2">
                    <code className="flex-1 bg-black/30 px-4 py-3 rounded-lg text-green-400 text-sm font-mono">
                      {createdKey.api_key}
                    </code>
                    <button
                      onClick={() => copyToClipboard(createdKey.api_key, 'key')}
                      className="p-3 bg-white/10 hover:bg-white/20 rounded-lg"
                      data-testid="copy-api-key"
                    >
                      {copiedField === 'key' ? <CheckCircle className="h-5 w-5 text-green-400" /> : <Copy className="h-5 w-5 text-gray-400" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">API Secret</label>
                  <div className="flex items-center space-x-2">
                    <code className="flex-1 bg-black/30 px-4 py-3 rounded-lg text-yellow-400 text-sm font-mono">
                      {showSecret ? createdKey.api_secret : '•'.repeat(64)}
                    </code>
                    <button
                      onClick={() => setShowSecret(!showSecret)}
                      className="p-3 bg-white/10 hover:bg-white/20 rounded-lg"
                    >
                      {showSecret ? <EyeOff className="h-5 w-5 text-gray-400" /> : <Eye className="h-5 w-5 text-gray-400" />}
                    </button>
                    <button
                      onClick={() => copyToClipboard(createdKey.api_secret, 'secret')}
                      className="p-3 bg-white/10 hover:bg-white/20 rounded-lg"
                      data-testid="copy-api-secret"
                    >
                      {copiedField === 'secret' ? <CheckCircle className="h-5 w-5 text-green-400" /> : <Copy className="h-5 w-5 text-gray-400" />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-6 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <p className="text-yellow-200 text-sm">
                  ⚠️ <strong>Important:</strong> Copy and save your API secret now. It will not be displayed again.
                </p>
              </div>

              <button
                onClick={() => { setCreatedKey(null); setShowSecret(false); }}
                className="w-full mt-6 bg-purple-600 hover:bg-purple-700 text-white py-3 rounded-xl font-semibold"
              >
                Done
              </button>
            </div>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* API Keys List */}
          <div className="lg:col-span-2">
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-bold text-white">API Keys</h2>
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg font-medium flex items-center space-x-2"
                  data-testid="create-key-btn"
                >
                  <Plus className="h-5 w-5" />
                  <span>Create Key</span>
                </button>
              </div>

              {/* Create Form */}
              {showCreateForm && (
                <form onSubmit={createApiKey} className="mb-6 p-4 bg-white/5 rounded-xl" data-testid="create-key-form">
                  <h3 className="text-lg font-semibold text-white mb-4">Create New API Key</h3>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">Name *</label>
                      <input
                        type="text"
                        value={newKeyName}
                        onChange={(e) => setNewKeyName(e.target.value)}
                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="My API Key"
                        required
                        data-testid="input-key-name"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
                      <input
                        type="text"
                        value={newKeyDescription}
                        onChange={(e) => setNewKeyDescription(e.target.value)}
                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="For my trading bot"
                        data-testid="input-key-description"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">Rate Limit (requests/hour)</label>
                      <input
                        type="number"
                        value={newKeyRateLimit}
                        onChange={(e) => setNewKeyRateLimit(parseInt(e.target.value))}
                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        min="1"
                        max="100000"
                        data-testid="input-key-rate-limit"
                      />
                    </div>
                  </div>
                  <div className="flex space-x-3 mt-4">
                    <button
                      type="submit"
                      disabled={creating}
                      className="bg-green-600 hover:bg-green-700 disabled:bg-green-600/50 text-white px-4 py-2 rounded-lg font-medium flex items-center space-x-2"
                      data-testid="submit-create-key"
                    >
                      {creating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Plus className="h-5 w-5" />}
                      <span>Create</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowCreateForm(false)}
                      className="text-gray-400 hover:text-white px-4 py-2"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {/* Keys List */}
              {loading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                </div>
              ) : apiKeys.length === 0 ? (
                <div className="text-center py-12">
                  <Key className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">No API keys yet</p>
                  <p className="text-gray-500 text-sm">Create your first API key to get started</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {apiKeys.map((key) => (
                    <div key={key.id} className="bg-white/5 rounded-xl p-4" data-testid={`api-key-${key.id}`}>
                      <div className="flex justify-between items-start">
                        <div>
                          <h4 className="text-white font-semibold">{key.name}</h4>
                          {key.description && <p className="text-gray-400 text-sm mt-1">{key.description}</p>}
                          <code className="text-purple-400 text-sm font-mono mt-2 block">{key.api_key}</code>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className={`text-xs px-2 py-1 rounded ${
                            key.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' :
                            key.status === 'REVOKED' ? 'bg-red-500/20 text-red-400' :
                            'bg-gray-500/20 text-gray-400'
                          }`}>
                            {key.status}
                          </span>
                          {key.status === 'ACTIVE' && (
                            <button
                              onClick={() => revokeKey(key.id)}
                              className="p-2 text-red-400 hover:bg-red-500/20 rounded-lg"
                              data-testid={`revoke-key-${key.id}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center space-x-4 mt-3 text-sm text-gray-500">
                        <span>Rate: {key.rate_limit}/hr</span>
                        <span>Used: {key.usage_count} times</span>
                        <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar - Documentation */}
          <div className="space-y-6">
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-white flex items-center mb-4">
                <BookOpen className="h-5 w-5 mr-2 text-purple-400" /> Quick Start
              </h3>
              <div className="space-y-4">
                <div>
                  <h4 className="text-gray-300 font-medium mb-2">1. HMAC Authentication</h4>
                  <p className="text-gray-500 text-sm">All ramp API calls require HMAC-SHA256 signature</p>
                </div>
                <div>
                  <h4 className="text-gray-300 font-medium mb-2">2. Required Headers</h4>
                  <ul className="text-gray-500 text-sm space-y-1">
                    <li>• X-API-KEY</li>
                    <li>• X-TIMESTAMP (Unix)</li>
                    <li>• X-SIGNATURE</li>
                  </ul>
                </div>
                <div>
                  <h4 className="text-gray-300 font-medium mb-2">3. Signature Formula</h4>
                  <code className="text-xs bg-black/30 px-2 py-1 rounded text-green-400 block">
                    HMAC-SHA256(timestamp + body, secret)
                  </code>
                </div>
              </div>
            </div>

            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-white flex items-center mb-4">
                <Code className="h-5 w-5 mr-2 text-purple-400" /> API Endpoints
              </h3>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <code className="text-purple-400">GET /api/ramp-api-health</code>
                </div>
                <div className="flex items-center justify-between">
                  <code className="text-purple-400">POST /api/ramp-api-onramp-quote</code>
                </div>
                <div className="flex items-center justify-between">
                  <code className="text-purple-400">POST /api/ramp-api-onramp</code>
                </div>
                <div className="flex items-center justify-between">
                  <code className="text-purple-400">POST /api/ramp-api-offramp-quote</code>
                </div>
                <div className="flex items-center justify-between">
                  <code className="text-purple-400">POST /api/ramp-api-offramp</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
