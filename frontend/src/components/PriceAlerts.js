import React, { useState, useEffect, useCallback } from 'react';
import { Bell, Plus, Trash2, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

const ASSETS = ['BTC', 'ETH', 'NENO', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX', 'DOT', 'LINK', 'MATIC'];

export default function PriceAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ asset: 'BTC', condition: 'above', threshold: '' });
  const [creating, setCreating] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/alerts`, { headers: headers() });
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts || []);
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const createAlert = async (e) => {
    e.preventDefault();
    if (!form.threshold) return;
    setCreating(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/alerts/create`, {
        method: 'POST', headers: headers(),
        body: JSON.stringify({ asset: form.asset, condition: form.condition, threshold: parseFloat(form.threshold) }),
      });
      if (res.ok) {
        setShowForm(false);
        setForm({ asset: 'BTC', condition: 'above', threshold: '' });
        fetchAlerts();
      }
    } catch (e) { console.error(e); }
    finally { setCreating(false); }
  };

  const deleteAlert = async (id) => {
    try {
      await fetch(`${BACKEND_URL}/api/alerts/${id}`, { method: 'DELETE', headers: headers() });
      fetchAlerts();
    } catch (e) { console.error(e); }
  };

  return (
    <div className="space-y-4" data-testid="price-alerts-section">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-amber-400" />
          <h3 className="text-white font-medium text-sm">Alert Prezzo</h3>
          <span className="text-xs text-gray-500">({alerts.filter(a => !a.triggered).length} attivi)</span>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs rounded-lg"
          data-testid="create-alert-btn">
          <Plus className="h-3 w-3" /> Nuovo Alert
        </button>
      </div>

      {showForm && (
        <form onSubmit={createAlert} className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3" data-testid="alert-form">
          <div className="grid grid-cols-3 gap-3">
            <select value={form.asset} onChange={e => setForm({ ...form, asset: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm" data-testid="alert-asset">
              {ASSETS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={form.condition} onChange={e => setForm({ ...form, condition: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm" data-testid="alert-condition">
              <option value="above">Sopra</option>
              <option value="below">Sotto</option>
            </select>
            <input type="number" step="0.01" value={form.threshold}
              onChange={e => setForm({ ...form, threshold: e.target.value })}
              placeholder="Prezzo EUR" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm"
              data-testid="alert-threshold" />
          </div>
          <button type="submit" disabled={creating}
            className="w-full py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm rounded-lg disabled:opacity-50"
            data-testid="alert-submit-btn">
            {creating ? <Loader2 className="h-4 w-4 animate-spin mx-auto" /> : 'Crea Alert'}
          </button>
        </form>
      )}

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-amber-400" /></div>
      ) : alerts.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-4">Nessun alert. Crea il tuo primo alert prezzo.</p>
      ) : (
        <div className="space-y-2">
          {alerts.map(a => (
            <div key={a.id} className={`flex items-center justify-between p-3 rounded-xl border ${
              a.triggered ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-white/[0.03] border-white/5'
            }`} data-testid={`alert-item-${a.id}`}>
              <div className="flex items-center gap-3">
                {a.condition === 'above'
                  ? <TrendingUp className={`h-4 w-4 ${a.triggered ? 'text-emerald-400' : 'text-cyan-400'}`} />
                  : <TrendingDown className={`h-4 w-4 ${a.triggered ? 'text-emerald-400' : 'text-red-400'}`} />}
                <div>
                  <span className="text-white text-sm font-medium">{a.asset}</span>
                  <span className="text-gray-400 text-xs mx-2">{a.condition === 'above' ? 'sopra' : 'sotto'}</span>
                  <span className="text-white text-sm tabular-nums">{new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(a.threshold)}</span>
                  {a.triggered && <span className="ml-2 text-[10px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded">SCATTATO</span>}
                </div>
              </div>
              {!a.triggered && (
                <button onClick={() => deleteAlert(a.id)} className="text-gray-500 hover:text-red-400" data-testid={`delete-alert-${a.id}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
