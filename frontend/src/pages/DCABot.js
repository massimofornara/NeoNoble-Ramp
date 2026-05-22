import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Plus, Pause, Play, Trash2, RefreshCw,
  TrendingUp, Clock, DollarSign, BarChart3, FileDown
} from 'lucide-react';
import { xhrGet, xhrPost, BACKEND_URL } from '../utils/safeFetch';

const ASSETS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'NENO', 'AVAX', 'DOT', 'LINK'];
const INTERVALS = [
  { id: 'hourly', label: 'Ogni ora' },
  { id: 'daily', label: 'Giornaliero' },
  { id: 'weekly', label: 'Settimanale' },
  { id: 'biweekly', label: 'Bisettimanale' },
  { id: 'monthly', label: 'Mensile' },
];

export default function DCABot() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState('plans');

  // Form
  const [asset, setAsset] = useState('BTC');
  const [amount, setAmount] = useState('');
  const [interval, setInterval] = useState('daily');
  const [maxExec, setMaxExec] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [pData, hData] = await Promise.all([
        xhrGet(`${BACKEND_URL}/api/dca/plans`),
        xhrGet(`${BACKEND_URL}/api/dca/history?limit=50`),
      ]);
      setPlans(pData.plans || []);
      setHistory(hData.executions || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreate = async () => {
    setCreating(true); setResult(null);
    try {
      const body = { asset, amount_eur: parseFloat(amount), interval };
      if (maxExec) body.max_executions = parseInt(maxExec);
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/dca/create`, body);
      if (!ok) throw new Error(data.detail || 'Errore creazione DCA');
      setResult({ ok: true, msg: data.message });
      setShowCreate(false); setAmount(''); setMaxExec('');
      fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setCreating(false); }
  };

  const handlePause = async (id) => {
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/dca/pause`, { plan_id: id });
      if (!ok) throw new Error(data.detail || 'Errore');
      fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleResume = async (id) => {
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/dca/resume`, { plan_id: id });
      if (!ok) throw new Error(data.detail || 'Errore');
      fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleCancel = async (id) => {
    if (!window.confirm('Vuoi cancellare questo piano DCA?')) return;
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/dca/cancel`, { plan_id: id });
      if (!ok) throw new Error(data.detail || 'Errore cancellazione');
      fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleDownloadPDF = () => {
    window.open(`${BACKEND_URL}/api/export/compliance/pdf?days=90`, '_blank');
  };

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="dca-bot-page">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg" data-testid="back-btn">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <div className="flex items-center gap-2">
            <h1 className="text-white font-bold text-base">DCA Trading Bot</h1>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">AUTO</span>
          </div>
          <div className="ml-auto flex gap-2">
            <button onClick={handleDownloadPDF} data-testid="pdf-download-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg text-xs font-medium hover:bg-purple-500/20">
              <FileDown className="w-3.5 h-3.5" /> Report PDF
            </button>
            <button onClick={() => setShowCreate(!showCreate)} data-testid="create-plan-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-xs font-bold">
              <Plus className="w-3.5 h-3.5" /> Nuovo Piano
            </button>
          </div>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="max-w-5xl mx-auto px-4 pt-3">
          <div className={`p-2.5 rounded-lg text-xs font-medium ${result.ok ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
            {result.msg}
          </div>
        </div>
      )}

      <div className="max-w-5xl mx-auto px-4 py-4 space-y-4">
        {/* Create Form */}
        {showCreate && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5" data-testid="create-dca-form">
            <h2 className="text-white font-bold text-sm mb-4">Crea Piano DCA</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-zinc-500 text-[10px] block mb-1">Asset</label>
                <select value={asset} onChange={e => setAsset(e.target.value)} data-testid="dca-asset"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm">
                  {ASSETS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div>
                <label className="text-zinc-500 text-[10px] block mb-1">EUR per Esecuzione</label>
                <input type="number" step="any" value={amount} onChange={e => setAmount(e.target.value)} placeholder="50.00"
                  data-testid="dca-amount" className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono" />
              </div>
              <div>
                <label className="text-zinc-500 text-[10px] block mb-1">Intervallo</label>
                <select value={interval} onChange={e => setInterval(e.target.value)} data-testid="dca-interval"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm">
                  {INTERVALS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-zinc-500 text-[10px] block mb-1">Max Esecuzioni (opz.)</label>
                <input type="number" value={maxExec} onChange={e => setMaxExec(e.target.value)} placeholder="illimitato"
                  data-testid="dca-max" className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleCreate} disabled={creating || !amount} data-testid="confirm-dca-btn"
                className="px-6 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-xs font-bold disabled:opacity-50">
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Attiva Piano'}
              </button>
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-zinc-400 text-xs hover:text-white">Annulla</button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-zinc-800">
          {[{ id: 'plans', label: `Piani (${plans.length})` }, { id: 'history', label: `Storico (${history.length})` }].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`dca-tab-${t.id}`}
              className={`px-4 py-2 text-xs font-medium transition-colors ${tab === t.id ? 'text-purple-400 border-b-2 border-purple-500' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Plans List */}
        {tab === 'plans' && (
          plans.length === 0 ? (
            <div className="py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-emerald-500/10 flex items-center justify-center">
                <RefreshCw className="w-8 h-8 text-emerald-400" />
              </div>
              <h2 className="text-white font-bold text-lg mb-2">Nessun piano DCA</h2>
              <p className="text-zinc-500 text-sm">Crea il tuo primo piano di accumulo automatico</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {plans.map(p => (
                <div key={p.id} data-testid={`plan-${p.id}`}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-violet-600/20 flex items-center justify-center text-white font-bold text-sm shrink-0">
                    {p.asset?.slice(0, 2)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-white font-bold text-sm">{p.asset}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                        p.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' :
                        p.status === 'paused' ? 'bg-yellow-500/20 text-yellow-400' :
                        p.status === 'completed' ? 'bg-blue-500/20 text-blue-400' :
                        'bg-zinc-700 text-zinc-400'
                      }`}>{p.status?.toUpperCase()}</span>
                    </div>
                    <div className="flex gap-4 text-[10px] text-zinc-500">
                      <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />{p.amount_eur} EUR</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{INTERVALS.find(i => i.id === p.interval)?.label || p.interval}</span>
                      <span className="flex items-center gap-1"><BarChart3 className="w-3 h-3" />{p.total_executions} esecuzioni</span>
                      <span className="flex items-center gap-1"><TrendingUp className="w-3 h-3" />Investiti: {p.total_invested_eur?.toFixed(2)} EUR</span>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {p.status === 'active' && (
                      <button onClick={() => handlePause(p.id)} title="Pausa" className="p-2 hover:bg-zinc-800 rounded-lg text-yellow-400">
                        <Pause className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {p.status === 'paused' && (
                      <button onClick={() => handleResume(p.id)} title="Riprendi" className="p-2 hover:bg-zinc-800 rounded-lg text-emerald-400">
                        <Play className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button onClick={() => handleCancel(p.id)} title="Cancella" className="p-2 hover:bg-zinc-800 rounded-lg text-red-400">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* History */}
        {tab === 'history' && (
          history.length === 0 ? (
            <div className="py-12 text-center text-zinc-600 text-xs">Nessuna esecuzione DCA registrata</div>
          ) : (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-zinc-800/50">
                  <tr>
                    <th className="px-3 py-2 text-left text-zinc-500 font-medium">Data</th>
                    <th className="px-3 py-2 text-left text-zinc-500 font-medium">Asset</th>
                    <th className="px-3 py-2 text-right text-zinc-500 font-medium">EUR</th>
                    <th className="px-3 py-2 text-right text-zinc-500 font-medium">Quantita</th>
                    <th className="px-3 py-2 text-right text-zinc-500 font-medium">Prezzo</th>
                    <th className="px-3 py-2 text-right text-zinc-500 font-medium">Fee</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {history.map(h => (
                    <tr key={h.id} className="hover:bg-zinc-800/30">
                      <td className="px-3 py-2 text-zinc-400">{h.executed_at?.slice(0, 16).replace('T', ' ')}</td>
                      <td className="px-3 py-2 text-zinc-200 font-medium">{h.asset}</td>
                      <td className="px-3 py-2 text-right text-zinc-300 font-mono">{h.amount_eur?.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-emerald-400 font-mono">{h.quantity?.toFixed(8)}</td>
                      <td className="px-3 py-2 text-right text-zinc-300 font-mono">{h.price?.toLocaleString()}</td>
                      <td className="px-3 py-2 text-right text-zinc-500 font-mono">{h.fee?.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
}
