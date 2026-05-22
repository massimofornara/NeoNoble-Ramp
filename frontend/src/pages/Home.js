import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ArrowRight, Coins, Shield, Zap, Globe, ChevronRight } from 'lucide-react';

const SUPPORTED_CRYPTOS = ['BTC', 'ETH', 'NENO', 'USDT', 'USDC', 'BNB', 'SOL'];

export default function Home() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Navigation */}
      <nav className="border-b border-white/10 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-2">
              <Coins className="h-8 w-8 text-purple-400" />
              <span className="text-xl font-bold text-white">NeoNoble Ramp</span>
            </div>
            <div className="flex items-center space-x-4">
              {isAuthenticated ? (
                <>
                  <Link
                    to="/dashboard"
                    className="text-gray-300 hover:text-white px-3 py-2"
                    data-testid="nav-dashboard"
                  >
                    Dashboard
                  </Link>
                  {(user?.role === 'DEVELOPER' || user?.role === 'ADMIN') && (
                    <Link
                      to="/dev"
                      className="text-gray-300 hover:text-white px-3 py-2"
                      data-testid="nav-dev-portal"
                    >
                      Dev Portal
                    </Link>
                  )}
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="text-gray-300 hover:text-white px-3 py-2"
                    data-testid="nav-login"
                  >
                    Login
                  </Link>
                  <Link
                    to="/signup"
                    className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg font-medium"
                    data-testid="nav-signup"
                  >
                    Get Started
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16">
        <div className="text-center">
          <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
            Buy & Sell Crypto
            <span className="block text-purple-400">Instantly</span>
          </h1>
          <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
            The most trusted platform for converting EUR to crypto and back.
            Fast, secure, and with real-time pricing.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-4">
            <button
              onClick={() => navigate(isAuthenticated ? '/dashboard' : '/signup')}
              className="bg-purple-600 hover:bg-purple-700 text-white px-8 py-4 rounded-xl font-semibold text-lg flex items-center justify-center space-x-2"
              data-testid="hero-get-started"
            >
              <span>{isAuthenticated ? 'Go to Dashboard' : 'Start Trading'}</span>
              <ArrowRight className="h-5 w-5" />
            </button>
            <Link
              to="/dev"
              className="border border-purple-500 text-purple-400 hover:bg-purple-500/10 px-8 py-4 rounded-xl font-semibold text-lg flex items-center justify-center space-x-2"
              data-testid="hero-dev-portal"
            >
              <span>Developer Portal</span>
              <ChevronRight className="h-5 w-5" />
            </Link>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-20">
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-6 text-center">
            <p className="text-3xl font-bold text-white">€10,000</p>
            <p className="text-gray-400 mt-1">NENO Fixed Price</p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-6 text-center">
            <p className="text-3xl font-bold text-white">1.5%</p>
            <p className="text-gray-400 mt-1">Trading Fee</p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-6 text-center">
            <p className="text-3xl font-bold text-white">15+</p>
            <p className="text-gray-400 mt-1">Cryptocurrencies</p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-6 text-center">
            <p className="text-3xl font-bold text-white">Live</p>
            <p className="text-gray-400 mt-1">Real-time Prices</p>
          </div>
        </div>
      </div>

      {/* Features */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <h2 className="text-3xl font-bold text-white text-center mb-12">Why Choose NeoNoble Ramp?</h2>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-8">
            <div className="bg-purple-500/20 w-12 h-12 rounded-lg flex items-center justify-center mb-4">
              <Zap className="h-6 w-6 text-purple-400" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Instant Quotes</h3>
            <p className="text-gray-400">
              Get real-time quotes from CoinGecko. NENO always at €10,000.
            </p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-8">
            <div className="bg-purple-500/20 w-12 h-12 rounded-lg flex items-center justify-center mb-4">
              <Shield className="h-6 w-6 text-purple-400" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">HMAC Security</h3>
            <p className="text-gray-400">
              Enterprise-grade API security with HMAC-SHA256 signatures and replay protection.
            </p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-xl p-8">
            <div className="bg-purple-500/20 w-12 h-12 rounded-lg flex items-center justify-center mb-4">
              <Globe className="h-6 w-6 text-purple-400" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Developer API</h3>
            <p className="text-gray-400">
              Integrate our ramp into your platform with our comprehensive REST API.
            </p>
          </div>
        </div>
      </div>

      {/* Supported Cryptos */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-2xl font-bold text-white text-center mb-8">Supported Cryptocurrencies</h2>
        <div className="flex flex-wrap justify-center gap-4">
          {SUPPORTED_CRYPTOS.map((crypto) => (
            <div
              key={crypto}
              className="bg-white/10 px-6 py-3 rounded-full text-white font-medium"
            >
              {crypto}
            </div>
          ))}
          <div className="bg-purple-500/30 px-6 py-3 rounded-full text-purple-300 font-medium">
            + more
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl p-12 text-center">
          <h2 className="text-3xl font-bold text-white mb-4">Ready to Start?</h2>
          <p className="text-white/80 mb-8 max-w-xl mx-auto">
            Join thousands of users converting EUR to crypto seamlessly.
          </p>
          <button
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/signup')}
            className="bg-white text-purple-600 px-8 py-4 rounded-xl font-semibold text-lg hover:bg-gray-100"
            data-testid="cta-button"
          >
            {isAuthenticated ? 'Go to Dashboard' : 'Create Free Account'}
          </button>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-white/10 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="flex items-center space-x-2 mb-4 md:mb-0">
              <Coins className="h-6 w-6 text-purple-400" />
              <span className="text-white font-semibold">NeoNoble Ramp</span>
            </div>
            <div className="flex space-x-6 text-gray-400 text-sm">
              <Link to="/dev" className="hover:text-white">Developer Portal</Link>
              <span>© 2024 NeoNoble</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
