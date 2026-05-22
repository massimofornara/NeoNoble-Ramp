import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  ArrowLeft, Loader2, Shield, ShieldCheck, Globe, Bell,
  Smartphone, Key, Copy, Check, Eye, EyeOff, Languages
} from 'lucide-react';
import { xhrGet, xhrPost, BACKEND_URL } from '../utils/safeFetch';

const LANGUAGES = [
  { code: 'it', label: 'Italiano', flag: 'IT' },
  { code: 'en', label: 'English', flag: 'EN' },
  { code: 'de', label: 'Deutsch', flag: 'DE' },
  { code: 'fr', label: 'Francais', flag: 'FR' },
  { code: 'es', label: 'Espanol', flag: 'ES' },
  { code: 'pt', label: 'Portugues', flag: 'PT' },
  { code: 'ja', label: 'Nihongo', flag: 'JA' },
  { code: 'zh', label: 'Zhongwen', flag: 'ZH' },
  { code: 'ar', label: 'Al-Arabiyya', flag: 'AR' },
];

export default function SettingsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState('security');
  const [loading, setLoading] = useState(true);

  // 2FA state
  const [twoFaStatus, setTwoFaStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [totpCode, setTotpCode] = useState('');
  const [backupCodes, setBackupCodes] = useState(null);
  const [showSecret, setShowSecret] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  // Language state
  const [lang, setLang] = useState(localStorage.getItem('neonoble_lang') || 'it');

  // Notification preferences
  const [notifPrefs, setNotifPrefs] = useState({
    trade_alerts: true, margin_alerts: true, kyc_updates: true,
    security_alerts: true, system_updates: false,
  });

  const fetchStatus = useCallback(async () => {
    try {
      const data = await xhrGet(`${BACKEND_URL}/api/auth/2fa/status`);
      setTwoFaStatus(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleSetup2FA = async () => {
    setResult(null);
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/auth/2fa/setup`, {});
      if (!ok) throw new Error(data.detail || 'Errore setup 2FA');
      setSetupData(data);
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleVerify2FA = async () => {
    setResult(null);
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/auth/2fa/verify`, { code: totpCode });
      if (!ok) throw new Error(data.detail || 'Codice non valido');
      setBackupCodes(data.backup_codes);
      setSetupData(null); setTotpCode('');
      fetchStatus();
      setResult({ ok: true, msg: data.message });
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleDisable2FA = async () => {
    if (!totpCode) { setResult({ ok: false, msg: 'Inserisci il codice TOTP' }); return; }
    setResult(null);
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/auth/2fa/disable`, { code: totpCode, password: '' });
      if (!ok) throw new Error(data.detail || 'Errore disabilitazione');
      setTotpCode(''); fetchStatus();
      setResult({ ok: true, msg: data.message });
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleLangChange = (code) => {
    setLang(code);
    localStorage.setItem('neonoble_lang', code);
    // In a real multi-lang app, this would trigger i18n context change
  };

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="settings-page">
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <h1 className="text-white font-bold text-lg">Impostazioni</h1>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-4">
        <div className="flex gap-1 bg-zinc-900 rounded-xl p-1 mb-6 w-fit">
          {[
            { id: 'security', label: 'Sicurezza', icon: Shield },
            { id: 'language', label: 'Lingua', icon: Globe },
            { id: 'notifications', label: 'Notifiche', icon: Bell },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t.id ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-400 hover:text-white'}`}>
              <t.icon className="w-4 h-4" />{t.label}
            </button>
          ))}
        </div>

        {result && (
          <div className={`p-3 rounded-lg text-sm mb-4 ${result.ok ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
            {result.msg}
          </div>
        )}

        {/* SECURITY TAB */}
        {tab === 'security' && (
          <div className="space-y-4" data-testid="security-tab">
            {/* 2FA Status Card */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${twoFaStatus?.enabled ? 'bg-emerald-500/20' : 'bg-zinc-800'}`}>
                    {twoFaStatus?.enabled ? <ShieldCheck className="w-5 h-5 text-emerald-400" /> : <Smartphone className="w-5 h-5 text-zinc-500" />}
                  </div>
                  <div>
                    <h3 className="text-white font-bold text-sm">Autenticazione a Due Fattori (TOTP)</h3>
                    <p className="text-zinc-500 text-xs">{twoFaStatus?.enabled ? 'Abilitata' : 'Disabilitata'}</p>
                  </div>
                </div>
                <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${twoFaStatus?.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 text-zinc-500'}`} data-testid="2fa-status">
                  {twoFaStatus?.enabled ? 'ATTIVA' : 'OFF'}
                </span>
              </div>

              {!twoFaStatus?.enabled && !setupData && (
                <button onClick={handleSetup2FA} data-testid="setup-2fa-btn"
                  className="w-full py-2.5 bg-gradient-to-r from-purple-500 to-violet-600 text-white rounded-xl font-bold text-sm hover:from-purple-600 hover:to-violet-700">
                  Configura 2FA
                </button>
              )}

              {/* Setup Flow */}
              {setupData && (
                <div className="space-y-4">
                  <div className="text-center">
                    <p className="text-zinc-400 text-xs mb-3">Scansiona il QR code con la tua app authenticator (Google Authenticator, Authy, etc.)</p>
                    {setupData.qr_code_base64 && (
                      <img src={setupData.qr_code_base64} alt="QR Code" className="w-48 h-48 mx-auto rounded-xl bg-white p-2" data-testid="qr-code" />
                    )}
                  </div>
                  <div className="bg-zinc-800 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-zinc-500 text-xs">Chiave Segreta</span>
                      <button onClick={() => setShowSecret(!showSecret)} className="text-zinc-400 hover:text-white">
                        {showSecret ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <code className="text-white text-xs font-mono flex-1">{showSecret ? setupData.secret : '**********************'}</code>
                      <button onClick={() => { navigator.clipboard.writeText(setupData.secret); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                        {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-zinc-400" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-zinc-400 text-xs block mb-1">Inserisci il codice dall'app</label>
                    <div className="flex gap-2">
                      <input type="text" value={totpCode} onChange={e => setTotpCode(e.target.value)} maxLength={6} placeholder="000000"
                        data-testid="totp-input"
                        className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-center text-lg font-mono tracking-[0.5em] focus:border-purple-500 focus:outline-none" />
                      <button onClick={handleVerify2FA} disabled={totpCode.length < 6} data-testid="verify-2fa-btn"
                        className="px-6 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-bold text-sm disabled:opacity-50">
                        Verifica
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Backup Codes */}
              {backupCodes && (
                <div className="mt-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4">
                  <h4 className="text-yellow-400 font-bold text-sm mb-2 flex items-center gap-2"><Key className="w-4 h-4" />Codici di Backup</h4>
                  <p className="text-zinc-400 text-xs mb-3">Salva questi codici in un posto sicuro. Ogni codice puo' essere usato una sola volta.</p>
                  <div className="grid grid-cols-4 gap-2">
                    {backupCodes.map((code, i) => (
                      <code key={i} className="bg-zinc-800 rounded px-2 py-1 text-center text-white text-xs font-mono">{code}</code>
                    ))}
                  </div>
                </div>
              )}

              {/* Disable */}
              {twoFaStatus?.enabled && !setupData && (
                <div className="mt-4 pt-4 border-t border-zinc-800">
                  <p className="text-zinc-500 text-xs mb-2">Codici backup rimanenti: {twoFaStatus.backup_codes_remaining}</p>
                  <div className="flex gap-2">
                    <input type="text" value={totpCode} onChange={e => setTotpCode(e.target.value)} maxLength={6} placeholder="Codice TOTP"
                      className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm font-mono" />
                    <button onClick={handleDisable2FA} data-testid="disable-2fa-btn"
                      className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg text-xs font-bold hover:bg-red-500/20">
                      Disabilita 2FA
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* LANGUAGE TAB */}
        {tab === 'language' && (
          <div className="space-y-3" data-testid="language-tab">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-4">
                <Languages className="w-5 h-5 text-purple-400" />
                <h3 className="text-white font-bold text-sm">Lingua dell'Interfaccia</h3>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {LANGUAGES.map(l => (
                  <button key={l.code} onClick={() => handleLangChange(l.code)} data-testid={`lang-${l.code}`}
                    className={`p-4 rounded-xl border text-left transition-all ${lang === l.code ? 'border-purple-500 bg-purple-500/10' : 'border-zinc-800 bg-zinc-800/50 hover:border-zinc-700'}`}>
                    <div className="flex items-center gap-3">
                      <span className="text-2xl font-bold text-zinc-300">{l.flag}</span>
                      <div>
                        <div className={`font-medium text-sm ${lang === l.code ? 'text-purple-400' : 'text-zinc-300'}`}>{l.label}</div>
                        <div className="text-zinc-500 text-[10px]">{l.code.toUpperCase()}</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* NOTIFICATIONS TAB */}
        {tab === 'notifications' && (
          <div className="space-y-3" data-testid="notifications-tab">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-4">
                <Bell className="w-5 h-5 text-purple-400" />
                <h3 className="text-white font-bold text-sm">Preferenze Notifiche</h3>
              </div>
              <div className="space-y-3">
                {[
                  { key: 'trade_alerts', label: 'Alert Trading', desc: 'Esecuzione ordini, riempimento trade' },
                  { key: 'margin_alerts', label: 'Alert Margin', desc: 'Liquidazione, margin call, PnL' },
                  { key: 'kyc_updates', label: 'Aggiornamenti KYC', desc: 'Stato verifica, approvazione' },
                  { key: 'security_alerts', label: 'Alert Sicurezza', desc: 'Login sospetto, cambio password, 2FA' },
                  { key: 'system_updates', label: 'Aggiornamenti Sistema', desc: 'Manutenzione, nuove funzionalita' },
                ].map(n => (
                  <div key={n.key} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
                    <div>
                      <div className="text-zinc-200 text-sm font-medium">{n.label}</div>
                      <div className="text-zinc-500 text-xs">{n.desc}</div>
                    </div>
                    <button
                      onClick={() => setNotifPrefs(p => ({ ...p, [n.key]: !p[n.key] }))}
                      data-testid={`notif-${n.key}`}
                      className={`relative w-11 h-6 rounded-full transition-colors ${notifPrefs[n.key] ? 'bg-purple-500' : 'bg-zinc-700'}`}
                    >
                      <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform ${notifPrefs[n.key] ? 'translate-x-[22px]' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
