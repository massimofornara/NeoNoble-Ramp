import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Lock, ArrowLeft, Loader2, CheckCircle, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { xhrPost, BACKEND_URL } from '../utils/safeFetch';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(true);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [tokenValid, setTokenValid] = useState(false);
  const [tokenEmail, setTokenEmail] = useState('');

  useEffect(() => {
    const verifyToken = async () => {
      if (!token) {
        setError('Token mancante. Richiedi un nuovo link di reset.');
        setVerifying(false);
        return;
      }
      try {
        const { ok, data } = await xhrPost(`${BACKEND_URL}/api/password/verify-token`, { token });

        if (ok) {
          setTokenValid(true);
          setTokenEmail(data.email);
        } else {
          setError(data.detail || 'Token non valido o scaduto');
        }
      } catch (err) {
        setError('Errore di verifica. Riprova più tardi.');
      } finally {
        setVerifying(false);
      }
    };

    verifyToken();
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) { setError('Le password non coincidono'); return; }
    if (password.length < 8) { setError('La password deve essere di almeno 8 caratteri'); return; }
    setLoading(true); setError('');
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/password/reset`, { token, new_password: password });
      if (ok) {
        setStatus('success');
        setTimeout(() => navigate('/login'), 3000);
      } else {
        setError(data.detail || 'Si è verificato un errore');
      }
    } catch (err) {
      setError('Errore di connessione. Riprova più tardi.');
    } finally {
      setLoading(false);
    }
  };

  // Loading state
  if (verifying) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center p-4">
        <div className="text-center">
          <Loader2 className="w-12 h-12 text-purple-400 animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Verifica del token in corso...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Back link */}
        <Link 
          to="/login" 
          className="inline-flex items-center text-gray-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Torna al login
        </Link>

        <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/10">
          {/* Header */}
          <div className="text-center mb-8">
            <div className={`w-16 h-16 ${status === 'success' ? 'bg-green-500/20' : 'bg-purple-500/20'} rounded-full flex items-center justify-center mx-auto mb-4`}>
              {status === 'success' ? (
                <CheckCircle className="w-8 h-8 text-green-400" />
              ) : (
                <Lock className="w-8 h-8 text-purple-400" />
              )}
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">
              {status === 'success' ? 'Password aggiornata!' : 'Reimposta password'}
            </h1>
            {tokenValid && !status && (
              <p className="text-gray-400">
                Crea una nuova password per <span className="text-purple-400">{tokenEmail}</span>
              </p>
            )}
          </div>

          {status === 'success' ? (
            /* Success State */
            <div className="text-center">
              <p className="text-gray-400 mb-6">
                La tua password è stata aggiornata con successo.
                Verrai reindirizzato al login...
              </p>
              <Link
                to="/login"
                className="inline-flex items-center justify-center w-full py-3 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-xl font-medium transition-colors"
              >
                Vai al login
              </Link>
            </div>
          ) : !tokenValid ? (
            /* Invalid Token State */
            <div className="text-center">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <AlertCircle className="w-8 h-8 text-red-400" />
              </div>
              <p className="text-red-400 mb-6">{error}</p>
              <Link
                to="/forgot-password"
                className="inline-flex items-center justify-center w-full py-3 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-xl font-medium transition-colors"
              >
                Richiedi nuovo link
              </Link>
            </div>
          ) : (
            /* Form */
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
                  Nuova Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimo 8 caratteri"
                    required
                    minLength={8}
                    className="w-full pl-10 pr-12 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 mb-2">
                  Conferma Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Ripeti la password"
                    required
                    className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !password || !confirmPassword}
                className="w-full py-3 px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Aggiornamento...
                  </>
                ) : (
                  'Reimposta password'
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
