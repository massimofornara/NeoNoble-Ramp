import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Coins, Mail, Lock, User, AlertCircle, Loader2, CheckCircle } from 'lucide-react';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('USER');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirect = searchParams.get('redirect') || (role === 'DEVELOPER' ? '/dev' : '/dashboard');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);
    const result = await register(email, password, role);
    setLoading(false);

    if (result.success) {
      navigate(role === 'DEVELOPER' ? '/dev' : '/dashboard');
    } else {
      setError(result.error || 'Registration failed');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center space-x-2">
            <Coins className="h-10 w-10 text-purple-400" />
            <span className="text-2xl font-bold text-white">NeoNoble Ramp</span>
          </Link>
          <h1 className="mt-6 text-3xl font-bold text-white">Create Account</h1>
          <p className="mt-2 text-gray-400">Join NeoNoble Ramp today</p>
        </div>

        <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8">
          {error && (
            <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center space-x-2 text-red-200" data-testid="signup-error">
              <AlertCircle className="h-5 w-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Role Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-3">I am a...</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setRole('USER')}
                className={`p-4 rounded-lg border-2 transition-all ${
                  role === 'USER'
                    ? 'border-purple-500 bg-purple-500/20'
                    : 'border-white/10 hover:border-white/30'
                }`}
                data-testid="role-user"
              >
                <User className={`h-6 w-6 mx-auto mb-2 ${role === 'USER' ? 'text-purple-400' : 'text-gray-400'}`} />
                <p className={`font-medium ${role === 'USER' ? 'text-white' : 'text-gray-300'}`}>User</p>
                <p className="text-xs text-gray-500 mt-1">Buy & sell crypto</p>
              </button>
              <button
                type="button"
                onClick={() => setRole('DEVELOPER')}
                className={`p-4 rounded-lg border-2 transition-all ${
                  role === 'DEVELOPER'
                    ? 'border-purple-500 bg-purple-500/20'
                    : 'border-white/10 hover:border-white/30'
                }`}
                data-testid="role-developer"
              >
                <Coins className={`h-6 w-6 mx-auto mb-2 ${role === 'DEVELOPER' ? 'text-purple-400' : 'text-gray-400'}`} />
                <p className={`font-medium ${role === 'DEVELOPER' ? 'text-white' : 'text-gray-300'}`}>Developer</p>
                <p className="text-xs text-gray-500 mt-1">Integrate our API</p>
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="you@example.com"
                  required
                  data-testid="signup-email"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="••••••••"
                  required
                  minLength={8}
                  data-testid="signup-password"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">At least 8 characters</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Confirm Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="••••••••"
                  required
                  data-testid="signup-confirm-password"
                />
                {password && confirmPassword && password === confirmPassword && (
                  <CheckCircle className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 text-green-400" />
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white py-3 rounded-lg font-semibold flex items-center justify-center space-x-2"
              data-testid="signup-submit"
            >
              {loading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Creating account...</span>
                </>
              ) : (
                <span>Create {role === 'DEVELOPER' ? 'Developer' : ''} Account</span>
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-gray-400">
              Already have an account?{' '}
              <Link to="/login" className="text-purple-400 hover:text-purple-300" data-testid="link-to-login">
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
