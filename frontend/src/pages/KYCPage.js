import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  ArrowLeft, Loader2, Shield, ShieldCheck, ShieldAlert, ShieldX,
  CheckCircle, XCircle, Clock, AlertTriangle, FileText,
  User, MapPin, CreditCard, Send, Eye, Ban
} from 'lucide-react';
import { xhrGet, xhrPost, BACKEND_URL } from '../utils/safeFetch';

const TIER_COLORS = {
  0: { bg: 'bg-zinc-500/20', text: 'text-zinc-400', border: 'border-zinc-500/30' },
  1: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  2: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  3: { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500/30' },
};

export default function KYCPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState('status');
  const [kycStatus, setKycStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  // Admin state
  const [pendingList, setPendingList] = useState([]);
  const [amlAlerts, setAmlAlerts] = useState([]);
  const [amlStats, setAmlStats] = useState(null);

  // KYC Form
  const [form, setForm] = useState({
    first_name: '', last_name: '', date_of_birth: '', nationality: '',
    address_line1: '', address_city: '', address_country: '', address_postal: '',
    tax_id: '', document_type: 'id_card', document_number: '',
  });

  const isAdmin = user?.role?.toUpperCase() === 'ADMIN';

  const fetchStatus = useCallback(async () => {
    try {
      const data = await xhrGet(`${BACKEND_URL}/api/kyc/status`);
      setKycStatus(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const fetchAdmin = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const [pData, aData, sData] = await Promise.all([
        xhrGet(`${BACKEND_URL}/api/kyc/admin/pending`),
        xhrGet(`${BACKEND_URL}/api/kyc/aml/alerts?status=open`),
        xhrGet(`${BACKEND_URL}/api/kyc/aml/stats`),
      ]);
      setPendingList(pData.pending || []);
      setAmlAlerts(aData.alerts || []);
      setAmlStats(sData);
    } catch (e) { console.error(e); }
  }, [isAdmin]);

  useEffect(() => { fetchStatus(); fetchAdmin(); }, [fetchStatus, fetchAdmin]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true); setResult(null);
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/kyc/submit`, form);
      if (!ok) throw new Error(data.detail || 'Errore invio KYC');
      setResult({ ok: true, msg: data.message });
      fetchStatus();
      setTab('status');
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setSubmitting(false); }
  };

  const handleReview = async (userId, action, tier) => {
    try {
      await xhrPost(`${BACKEND_URL}/api/kyc/admin/review`, { user_id: userId, action, new_tier: tier });
      fetchAdmin(); fetchStatus();
    } catch (e) { console.error(e); }
  };

  const handleAmlAction = async (alertId, action) => {
    try {
      await xhrPost(`${BACKEND_URL}/api/kyc/aml/review`, { alert_id: alertId, action });
      fetchAdmin();
    } catch (e) { console.error(e); }
  };

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  const tc = TIER_COLORS[kycStatus?.tier || 0];

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="kyc-page">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg" data-testid="back-btn">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-purple-400" />
            <h1 className="text-white font-bold text-lg">KYC / AML Compliance</h1>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-4">
        {/* Tabs */}
        <div className="flex gap-1 bg-zinc-900 rounded-xl p-1 mb-6 w-fit">
          {[
            { id: 'status', label: 'Il Mio KYC' },
            ...(kycStatus?.status !== 'approved' ? [{ id: 'submit', label: 'Invia Documenti' }] : []),
            ...(isAdmin ? [{ id: 'admin', label: 'Admin Review' }, { id: 'aml', label: 'AML Alerts' }] : []),
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t.id ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-400 hover:text-white'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {result && (
          <div className={`p-3 rounded-lg text-sm mb-4 ${result.ok ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
            {result.msg}
          </div>
        )}

        {/* STATUS TAB */}
        {tab === 'status' && kycStatus && (
          <div className="space-y-4" data-testid="kyc-status-tab">
            {/* Tier Card */}
            <div className={`p-6 rounded-2xl border ${tc.border} bg-zinc-900`}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${tc.bg} flex items-center justify-center`}>
                    {kycStatus.tier >= 2 ? <ShieldCheck className={`w-6 h-6 ${tc.text}`} /> : kycStatus.tier === 1 ? <Shield className={`w-6 h-6 ${tc.text}`} /> : <ShieldX className="w-6 h-6 text-zinc-500" />}
                  </div>
                  <div>
                    <div className="text-white font-bold text-lg">Tier {kycStatus.tier} — {kycStatus.tier_label}</div>
                    <div className="text-zinc-500 text-xs mt-0.5">
                      {kycStatus.status === 'approved' && 'Verificato'}
                      {kycStatus.status === 'pending' && 'In attesa di revisione'}
                      {kycStatus.status === 'rejected' && 'Rifiutato'}
                      {kycStatus.status === 'not_started' && 'Verifica non iniziata'}
                      {kycStatus.status === 'info_requested' && 'Informazioni richieste'}
                    </div>
                  </div>
                </div>
                <div className={`px-3 py-1 rounded-full text-xs font-bold ${
                  kycStatus.status === 'approved' ? 'bg-emerald-500/20 text-emerald-400' :
                  kycStatus.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                  kycStatus.status === 'rejected' ? 'bg-red-500/20 text-red-400' :
                  'bg-zinc-500/20 text-zinc-400'
                }`} data-testid="kyc-status-badge">
                  {kycStatus.status?.toUpperCase()}
                </div>
              </div>

              {/* Progress */}
              <div className="grid grid-cols-4 gap-2 mb-4">
                {[0, 1, 2, 3].map(t => (
                  <div key={t} className={`h-1.5 rounded-full ${t <= kycStatus.tier ? 'bg-purple-500' : 'bg-zinc-800'}`} />
                ))}
              </div>

              {/* Limits */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <div className="text-zinc-500 mb-1">Limite Giornaliero</div>
                  <div className="text-white font-bold" data-testid="daily-limit">
                    {kycStatus.daily_limit === -1 ? 'Illimitato' : `EUR ${kycStatus.daily_limit?.toLocaleString()}`}
                  </div>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <div className="text-zinc-500 mb-1">Utilizzato Oggi</div>
                  <div className="text-white font-bold" data-testid="daily-used">EUR {kycStatus.daily_used?.toLocaleString()}</div>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <div className="text-zinc-500 mb-1">Trading</div>
                  <div className={`font-bold ${kycStatus.can_trade ? 'text-emerald-400' : 'text-red-400'}`}>
                    {kycStatus.can_trade ? 'Abilitato' : 'Disabilitato'}
                  </div>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <div className="text-zinc-500 mb-1">Prelievi</div>
                  <div className={`font-bold ${kycStatus.can_withdraw ? 'text-emerald-400' : 'text-red-400'}`}>
                    {kycStatus.can_withdraw ? 'Abilitati' : 'Disabilitati'}
                  </div>
                </div>
              </div>

              {kycStatus.rejection_reason && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-xs">
                  <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
                  {kycStatus.rejection_reason}
                </div>
              )}
            </div>

            {/* Tier roadmap */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
              <h3 className="text-white font-bold text-sm mb-3">Livelli di Verifica</h3>
              <div className="space-y-2">
                {[
                  { tier: 0, label: 'Non Verificato', desc: 'Solo visualizzazione', limit: '0 EUR' },
                  { tier: 1, label: 'Base', desc: 'Email + Dati personali', limit: '1.000 EUR/giorno' },
                  { tier: 2, label: 'Verificato', desc: 'Documento di identita', limit: '50.000 EUR/giorno' },
                  { tier: 3, label: 'Premium', desc: 'Enhanced Due Diligence', limit: 'Illimitato' },
                ].map(t => (
                  <div key={t.tier} className={`flex items-center gap-3 p-3 rounded-lg ${kycStatus.tier >= t.tier ? 'bg-purple-500/5 border border-purple-500/20' : 'bg-zinc-800/30'}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${kycStatus.tier >= t.tier ? 'bg-purple-500/20 text-purple-400' : 'bg-zinc-800 text-zinc-600'}`}>
                      {t.tier}
                    </div>
                    <div className="flex-1">
                      <div className={`text-sm font-medium ${kycStatus.tier >= t.tier ? 'text-white' : 'text-zinc-500'}`}>{t.label}</div>
                      <div className="text-zinc-500 text-[10px]">{t.desc}</div>
                    </div>
                    <div className="text-xs text-zinc-400">{t.limit}</div>
                    {kycStatus.tier >= t.tier && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SUBMIT TAB */}
        {tab === 'submit' && (
          <form onSubmit={handleSubmit} data-testid="kyc-form" className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
            <h3 className="text-white font-bold text-sm flex items-center gap-2"><FileText className="w-4 h-4 text-purple-400" />Verifica Identita</h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Nome</label>
                <input type="text" value={form.first_name} onChange={e => setForm(f => ({...f, first_name: e.target.value}))} required
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Cognome</label>
                <input type="text" value={form.last_name} onChange={e => setForm(f => ({...f, last_name: e.target.value}))} required
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Data di Nascita</label>
                <input type="date" value={form.date_of_birth} onChange={e => setForm(f => ({...f, date_of_birth: e.target.value}))} required
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Nazionalita</label>
                <input type="text" value={form.nationality} onChange={e => setForm(f => ({...f, nationality: e.target.value}))} required placeholder="IT"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
            </div>

            <h4 className="text-zinc-400 text-xs font-medium flex items-center gap-1 pt-2"><MapPin className="w-3 h-3" />Indirizzo</h4>
            <input type="text" value={form.address_line1} onChange={e => setForm(f => ({...f, address_line1: e.target.value}))} required placeholder="Via/Piazza"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
            <div className="grid grid-cols-3 gap-3">
              <input type="text" value={form.address_city} onChange={e => setForm(f => ({...f, address_city: e.target.value}))} required placeholder="Citta"
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              <input type="text" value={form.address_country} onChange={e => setForm(f => ({...f, address_country: e.target.value}))} required placeholder="Paese (IT)"
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              <input type="text" value={form.address_postal} onChange={e => setForm(f => ({...f, address_postal: e.target.value}))} required placeholder="CAP"
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
            </div>

            <h4 className="text-zinc-400 text-xs font-medium flex items-center gap-1 pt-2"><CreditCard className="w-3 h-3" />Documento</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Tipo Documento</label>
                <select value={form.document_type} onChange={e => setForm(f => ({...f, document_type: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm">
                  <option value="id_card">Carta d'Identita</option>
                  <option value="passport">Passaporto</option>
                  <option value="drivers_license">Patente</option>
                </select>
              </div>
              <div>
                <label className="text-zinc-500 text-xs block mb-1">Numero Documento</label>
                <input type="text" value={form.document_number} onChange={e => setForm(f => ({...f, document_number: e.target.value}))} required
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
            </div>

            <div>
              <label className="text-zinc-500 text-xs block mb-1">Codice Fiscale (opzionale)</label>
              <input type="text" value={form.tax_id} onChange={e => setForm(f => ({...f, tax_id: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" placeholder="FRNTST93..." />
            </div>

            <button type="submit" disabled={submitting} data-testid="kyc-submit-btn"
              className="w-full py-3 bg-gradient-to-r from-purple-500 to-violet-600 text-white rounded-xl font-bold disabled:opacity-50 hover:from-purple-600 hover:to-violet-700 transition-all">
              {submitting ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Invia per Verifica'}
            </button>
          </form>
        )}

        {/* ADMIN REVIEW TAB */}
        {tab === 'admin' && isAdmin && (
          <div className="space-y-3" data-testid="admin-kyc-tab">
            <h3 className="text-white font-bold text-sm mb-2">Richieste KYC in Attesa ({pendingList.length})</h3>
            {pendingList.length === 0 && <div className="text-zinc-500 text-sm py-6 text-center">Nessuna richiesta in attesa</div>}
            {pendingList.map(p => (
              <div key={p.user_id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid={`pending-${p.user_id}`}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="text-white font-medium text-sm">{p.first_name} {p.last_name}</div>
                    <div className="text-zinc-500 text-xs">{p.email} - Tier {p.tier}</div>
                  </div>
                  <span className="text-yellow-400 text-xs font-bold">PENDING</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs mb-3">
                  <div><span className="text-zinc-500">Nazionalita:</span> <span className="text-zinc-300">{p.nationality}</span></div>
                  <div><span className="text-zinc-500">Nato:</span> <span className="text-zinc-300">{p.date_of_birth}</span></div>
                  <div><span className="text-zinc-500">Doc:</span> <span className="text-zinc-300">{p.document?.type} - {p.document?.number}</span></div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleReview(p.user_id, 'approve', Math.min((p.tier || 0) + 1, 3))}
                    className="flex-1 py-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-xs font-bold hover:bg-emerald-500/20">
                    Approva (Tier {Math.min((p.tier || 0) + 1, 3)})
                  </button>
                  <button onClick={() => handleReview(p.user_id, 'reject')}
                    className="flex-1 py-1.5 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg text-xs font-bold hover:bg-red-500/20">
                    Rifiuta
                  </button>
                  <button onClick={() => handleReview(p.user_id, 'request_info')}
                    className="flex-1 py-1.5 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-lg text-xs font-bold hover:bg-yellow-500/20">
                    Richiedi Info
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* AML ALERTS TAB */}
        {tab === 'aml' && isAdmin && (
          <div className="space-y-4" data-testid="aml-tab">
            {/* Stats */}
            {amlStats && (
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Alert Aperti', value: amlStats.open_alerts, color: 'text-yellow-400' },
                  { label: 'Escalated', value: amlStats.escalated, color: 'text-orange-400' },
                  { label: 'Utenti Bloccati', value: amlStats.blocked_users, color: 'text-red-400' },
                  { label: 'Totale Alert', value: amlStats.total_alerts, color: 'text-zinc-300' },
                ].map(s => (
                  <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-center">
                    <div className={`text-2xl font-bold font-mono ${s.color}`} data-testid={`aml-stat-${s.label.toLowerCase().replace(/ /g,'-')}`}>{s.value}</div>
                    <div className="text-zinc-500 text-xs mt-1">{s.label}</div>
                  </div>
                ))}
              </div>
            )}

            <h3 className="text-white font-bold text-sm">Alert AML Aperti ({amlAlerts.length})</h3>
            {amlAlerts.length === 0 && <div className="text-zinc-500 text-sm py-6 text-center">Nessun alert aperto</div>}
            {amlAlerts.map(a => (
              <div key={a.id} className={`bg-zinc-900 border rounded-xl p-4 ${a.severity === 'high' ? 'border-red-500/30' : 'border-yellow-500/30'}`} data-testid={`alert-${a.id}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className={`w-4 h-4 ${a.severity === 'high' ? 'text-red-400' : 'text-yellow-400'}`} />
                    <span className="text-white font-medium text-sm capitalize">{a.type?.replace('_', ' ')}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${a.severity === 'high' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                      {a.severity?.toUpperCase()}
                    </span>
                  </div>
                  <span className="text-zinc-500 text-xs">{a.created_at ? new Date(a.created_at).toLocaleString('it-IT') : ''}</span>
                </div>
                <p className="text-zinc-400 text-xs mb-2">{a.description}</p>
                <div className="text-xs text-zinc-500 mb-3">Utente: {a.user_id} | EUR {a.eur_value?.toLocaleString()} | {a.tx_type}</div>
                <div className="flex gap-2">
                  <button onClick={() => handleAmlAction(a.id, 'dismiss')}
                    className="px-3 py-1 bg-zinc-800 text-zinc-400 rounded-lg text-xs hover:bg-zinc-700">Archivia</button>
                  <button onClick={() => handleAmlAction(a.id, 'escalate')}
                    className="px-3 py-1 bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded-lg text-xs hover:bg-orange-500/20">Escalate</button>
                  <button onClick={() => handleAmlAction(a.id, 'block_user')}
                    className="px-3 py-1 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg text-xs hover:bg-red-500/20">Blocca Utente</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
