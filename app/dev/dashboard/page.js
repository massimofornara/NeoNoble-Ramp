'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function DevDashboard() {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');

    if (!token || !userData) {
      router.push('/dev/login');
      return;
    }

    setUser(JSON.parse(userData));
    fetchStats(token);
  }, [router]);

  const fetchStats = async (token) => {
    try {
      const response = await fetch('/api/dev/api-keys', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch stats');
      }

      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/dev/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="bg-indigo-600 text-white p-2 rounded-lg">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">NeoNoble Dev Portal</h1>
                <p className="text-sm text-gray-500">{user?.email}</p>
              </div>
            </div>
            <Button variant="outline" onClick={handleLogout}>
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b">
        <div className="container mx-auto px-4">
          <div className="flex space-x-8">
            <Link
              href="/dev/dashboard"
              className="px-3 py-4 text-sm font-medium text-indigo-600 border-b-2 border-indigo-600"
            >
              Dashboard
            </Link>
            <Link
              href="/dev/api-keys"
              className="px-3 py-4 text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              API Keys
            </Link>
            <Link
              href="/dev/docs"
              className="px-3 py-4 text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              Documentation
            </Link>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Dashboard</h2>
          <p className="text-gray-600">Welcome to your NeoNoble developer dashboard</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>API Keys</CardDescription>
              <CardTitle className="text-3xl">{stats?.apiClients?.length || 0}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600">Active API keys</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Total API Calls</CardDescription>
              <CardTitle className="text-3xl">
                {stats?.apiClients?.reduce((sum, client) => sum + client.totalCalls, 0) || 0}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600">Across all keys</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Total Fees Earned</CardDescription>
              <CardTitle className="text-3xl">
                €{stats?.apiClients?.reduce((sum, client) => sum + parseFloat(client.totalFeeBase), 0).toFixed(2) || '0.00'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600">From ramp transactions</p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Quick Start</CardTitle>
            <CardDescription>Get started with NeoNoble Ramp API in minutes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-start space-x-4">
              <div className="bg-indigo-100 text-indigo-600 rounded-full w-8 h-8 flex items-center justify-center font-bold flex-shrink-0">
                1
              </div>
              <div>
                <h4 className="font-medium text-gray-900 mb-1">Create an API Key</h4>
                <p className="text-sm text-gray-600">Generate your API credentials in the API Keys section</p>
                <Link href="/dev/api-keys">
                  <Button variant="link" className="px-0 h-auto mt-2">
                    Go to API Keys →
                  </Button>
                </Link>
              </div>
            </div>

            <div className="flex items-start space-x-4">
              <div className="bg-indigo-100 text-indigo-600 rounded-full w-8 h-8 flex items-center justify-center font-bold flex-shrink-0">
                2
              </div>
              <div>
                <h4 className="font-medium text-gray-900 mb-1">Read the Documentation</h4>
                <p className="text-sm text-gray-600">Learn how to integrate NENO onramp/offramp with HMAC authentication</p>
                <Link href="/dev/docs">
                  <Button variant="link" className="px-0 h-auto mt-2">
                    View Documentation →
                  </Button>
                </Link>
              </div>
            </div>

            <div className="flex items-start space-x-4">
              <div className="bg-indigo-100 text-indigo-600 rounded-full w-8 h-8 flex items-center justify-center font-bold flex-shrink-0">
                3
              </div>
              <div>
                <h4 className="font-medium text-gray-900 mb-1">Start Building</h4>
                <p className="text-sm text-gray-600">Integrate crypto on/off-ramp into your application</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}