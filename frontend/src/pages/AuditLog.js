import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Search, Download, Filter,
  Shield, Activity, Clock, AlertTriangle, Users,
  CreditCard, BarChart3, RefreshCw, ChevronLeft, ChevronRight
} from 'lucide-react';
import { xhrGet, getAuthHeaders, BACKEND_URL } from '../utils/safeFetch';

export default function AuditLog() {
  const navigate = useNavigate();
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [filterEmail, setFilterEmail] = useState('');
  const [filterType, setFilterType] = useState('');
  const [tab, setTab] = useState('logs');

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      let url = `${BACKEND_URL}/api/admin/audit/logs?page=${page}&page_size=30`;
      if (filterEmail) url += `&user_email=${encodeURIComponent(filterEmail)}`;
      if (filterType) url += `&event_type=${encodeURIComponent(filterType)}`;
      const data = await xhrGet(url);
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [page, filterEmail, filterType]);

  const fetchStats = useCallback(async () => {
    try {
      const data = await xhrGet(`${BACKEND_URL}/api/admin/audit/stats`);
      if (data && !data.detail) setStats(data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchLogs(); fetchStats(); }, [fetchLogs, fetchStats]);

  const handleExport = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/audit/export/csv?days=30`, { headers: getAuthHeaders() });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'audit_export.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { console.error(e); }
  };

  const sourceColors = {
    notification: 'bg-blue-500/20 text-blue-400',
    neno_exchange: 'bg-purple-500/20 text-purple-400',
    banking: 'bg-emerald-500/20 text-emerald-400',
    kyc: 'bg-amber-500/20 text-amber-400',
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900" data-testid="audit-log-page">
      <header className="border-b border-white/10 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-16 gap-4">
          <button onClick={() => navigate('/admin')} className="text-gray-400 hover:text-white" data-testid="audit-back-btn">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <Shield className="h-6 w-6 text-purple-400" />
          <h1 className="text-xl font-bold text-white">Registro Audit</h1>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
            {[
              { label: 'Utenti', value: stats.total_users, icon: Users, color: 'text-blue-400' },
              { label: 'Tx NENO', value: stats.total_neno_transactions, icon: Activity, color: 'text-purple-400' },
              { label: 'Tx Banking', value: stats.total_banking_transactions, icon: CreditCard, color: 'text-emerald-400' },
              { label: 'KYC Pending', value: stats.kyc_pending, icon: Clock, color: 'text-amber-400' },
              { label: 'AML Alerts', value: stats.aml_alerts, icon: AlertTriangle, color: 'text-red-400' },
              { label: 'Margin Aperte', value: stats.active_margin_positions, icon: BarChart3, color: 'text-cyan-400' },
            ].map((s, i) => (
              <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4" data-testid={`stat-${s.label.toLowerCase().replace(/\s/g, '-')}`}>
                <div className="flex items-center gap-2 mb-1">
                  <s.icon className={`h-4 w-4 ${s.color}`} />
                  <span className="text-gray-400 text-xs">{s.label}</span>
                </div>
                <div className="text-xl font-bold text-white">{s.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs & Filters */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="flex gap-2">
            {['logs', 'stats'].map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === t ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
                data-testid={`tab-${t}`}>
                {t === 'logs' ? 'Log Eventi' : 'Statistiche'}
              </button>
            ))}
          </div>
          <div className="flex-1 flex gap-2">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <input type="text" value={filterEmail} onChange={e => { setFilterEmail(e.target.value); setPage(1); }}
                className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="Filtra per email..." data-testid="filter-email" />
            </div>
            <select value={filterType} onChange={e => { setFilterType(e.target.value); setPage(1); }}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              data-testid="filter-type">
              <option value="">Tutti i tipi</option>
              <option value="trade">Trade</option>
              <option value="margin">Margin</option>
              <option value="kyc">KYC</option>
              <option value="security">Security</option>
              <option value="system">System</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={fetchLogs} className="p-2 bg-white/5 border border-white/10 rounded-lg text-gray-400 hover:text-white" data-testid="refresh-btn">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleExport} className="flex items-center gap-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium" data-testid="export-csv-btn">
              <Download className="h-4 w-4" /> CSV
            </button>
          </div>
        </div>

        {/* Logs Table */}
        {tab === 'logs' && (
          <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="audit-table">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Timestamp</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Sorgente</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Tipo</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Utente</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Dettagli</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={6} className="text-center py-12"><Loader2 className="h-6 w-6 animate-spin text-purple-400 mx-auto" /></td></tr>
                  ) : logs.length === 0 ? (
                    <tr><td colSpan={6} className="text-center py-12 text-gray-500">Nessun log trovato</td></tr>
                  ) : logs.map((log, i) => (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5" data-testid={`log-row-${i}`}>
                      <td className="px-4 py-3 text-gray-300 whitespace-nowrap text-xs">
                        {log.created_at ? new Date(log.created_at).toLocaleString('it-IT') : '-'}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded ${sourceColors[log.source] || 'bg-gray-500/20 text-gray-400'}`}>
                          {log.source || 'unknown'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-white">{log.type || log.title || '-'}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{log.user_id ? log.user_id.substring(0, 8) + '...' : '-'}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">
                        {log.message || log.neno_amount ? `${log.neno_amount} NENO` : log.amount ? `${log.amount} EUR` : '-'}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          (log.status === 'completed' || log.status === 'verified') ? 'bg-green-500/20 text-green-400' :
                          log.status === 'processing' ? 'bg-yellow-500/20 text-yellow-400' :
                          log.status === 'open' ? 'bg-blue-500/20 text-blue-400' :
                          'bg-gray-500/20 text-gray-400'
                        }`}>
                          {log.status || '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-white/10">
              <span className="text-gray-500 text-sm">{total} risultati totali</span>
              <div className="flex gap-2">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="p-1 rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-30" data-testid="page-prev">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-gray-400 text-sm px-2 py-1">Pagina {page}</span>
                <button onClick={() => setPage(p => p + 1)} disabled={logs.length < 30}
                  className="p-1 rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-30" data-testid="page-next">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Stats tab */}
        {tab === 'stats' && stats && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white/5 border border-white/10 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Attivita 24h</h3>
              <div className="space-y-3">
                <div className="flex justify-between"><span className="text-gray-400">Transazioni NENO</span><span className="text-white font-medium">{stats.neno_txs_24h}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Posizioni Margin Aperte</span><span className="text-white font-medium">{stats.active_margin_positions}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Carte Emesse</span><span className="text-white font-medium">{stats.total_cards_issued}</span></div>
              </div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Compliance</h3>
              <div className="space-y-3">
                <div className="flex justify-between"><span className="text-gray-400">KYC Approvati</span><span className="text-green-400 font-medium">{stats.kyc_approved}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">KYC In Attesa</span><span className="text-amber-400 font-medium">{stats.kyc_pending}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Alert AML</span><span className="text-red-400 font-medium">{stats.aml_alerts}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Transazioni Banking 7g</span><span className="text-white font-medium">{stats.bank_txs_7d}</span></div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
