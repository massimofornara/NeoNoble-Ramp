'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';

export default function ApiKeysPage() {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [apiClients, setApiClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showCredentialsDialog, setShowCredentialsDialog] = useState(false);
  const [newApiName, setNewApiName] = useState('');
  const [newCredentials, setNewCredentials] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');

    if (!token || !userData) {
      router.push('/dev/login');
      return;
    }

    setUser(JSON.parse(userData));
    fetchApiKeys(token);
  }, [router]);

  const fetchApiKeys = async (token) => {
    try {
      const response = await fetch('/api/dev/api-keys', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to fetch API keys');

      const data = await response.json();
      setApiClients(data.apiClients);
    } catch (error) {
      console.error('Failed to fetch API keys:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!newApiName.trim()) return;

    setCreating(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/dev/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: newApiName }),
      });

      if (!response.ok) throw new Error('Failed to create API key');

      const data = await response.json();
      setNewCredentials(data.apiClient);
      setShowCreateDialog(false);
      setShowCredentialsDialog(true);
      setNewApiName('');
      
      // Refresh list
      fetchApiKeys(token);
    } catch (error) {
      console.error('Failed to create API key:', error);
      alert('Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/dev/login');
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
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
              className="px-3 py-4 text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              Dashboard
            </Link>
            <Link
              href="/dev/api-keys"
              className="px-3 py-4 text-sm font-medium text-indigo-600 border-b-2 border-indigo-600"
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
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">API Keys</h2>
            <p className="text-gray-600">Manage your NeoNoble Ramp API credentials</p>
          </div>
          <Button onClick={() => setShowCreateDialog(true)}>
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create API Key
          </Button>
        </div>

        {apiClients.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="text-gray-400 mb-4">
                <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No API keys yet</h3>
              <p className="text-gray-600 mb-4">Create your first API key to start using the NeoNoble Ramp API</p>
              <Button onClick={() => setShowCreateDialog(true)}>Create Your First API Key</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {apiClients.map((client) => (
              <Card key={client.id}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-lg">{client.name}</CardTitle>
                      <CardDescription>
                        Created {new Date(client.createdAt).toLocaleDateString()}
                        {client.lastUsedAt && ` • Last used ${new Date(client.lastUsedAt).toLocaleDateString()}`}
                      </CardDescription>
                    </div>
                    <Badge variant={client.status === 'ACTIVE' ? 'default' : 'secondary'}>
                      {client.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-gray-500">API Key</Label>
                    <div className="flex items-center space-x-2 mt-1">
                      <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono">
                        {client.apiKey}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => copyToClipboard(client.apiKey)}
                      >
                        Copy
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-4 pt-4 border-t">
                    <div>
                      <p className="text-xs text-gray-500">Total Calls</p>
                      <p className="text-lg font-semibold">{client.totalCalls}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Total Fees</p>
                      <p className="text-lg font-semibold">€{parseFloat(client.totalFeeBase).toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Rate Limit</p>
                      <p className="text-lg font-semibold">{client.rateLimitDay}/day</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      {/* Create API Key Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Give your API key a name to help you identify it later
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="api-name">API Key Name</Label>
              <Input
                id="api-name"
                placeholder="e.g., Production Key"
                value={newApiName}
                onChange={(e) => setNewApiName(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateApiKey} disabled={!newApiName.trim() || creating}>
              {creating ? 'Creating...' : 'Create API Key'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Credentials Dialog */}
      <Dialog open={showCredentialsDialog} onOpenChange={setShowCredentialsDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>API Credentials Created</DialogTitle>
            <DialogDescription>
              Store these credentials securely. The API secret will not be shown again.
            </DialogDescription>
          </DialogHeader>
          {newCredentials && (
            <div className="space-y-4 py-4">
              <Alert>
                <AlertDescription className="text-sm">
                  <strong>Important:</strong> Copy your API secret now. You won't be able to see it again.
                </AlertDescription>
              </Alert>
              <div>
                <Label className="text-sm font-medium">API Key</Label>
                <div className="flex items-center space-x-2 mt-2">
                  <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono break-all">
                    {newCredentials.apiKey}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => copyToClipboard(newCredentials.apiKey)}
                  >
                    Copy
                  </Button>
                </div>
              </div>
              <div>
                <Label className="text-sm font-medium">API Secret</Label>
                <div className="flex items-center space-x-2 mt-2">
                  <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono break-all">
                    {newCredentials.apiSecret}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => copyToClipboard(newCredentials.apiSecret)}
                  >
                    Copy
                  </Button>
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setShowCredentialsDialog(false)}>I've Saved My Credentials</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}