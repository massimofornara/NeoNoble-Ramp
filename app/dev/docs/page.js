'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function DocsPage() {
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');

    if (!token || !userData) {
      router.push('/dev/login');
      return;
    }

    setUser(JSON.parse(userData));
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/dev/login');
  };

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
              className="px-3 py-4 text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              API Keys
            </Link>
            <Link
              href="/dev/docs"
              className="px-3 py-4 text-sm font-medium text-indigo-600 border-b-2 border-indigo-600"
            >
              Documentation
            </Link>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8 max-w-5xl">
        <div className="mb-8">
          <h2 className="text-3xl font-bold text-gray-900 mb-2">API Documentation</h2>
          <p className="text-gray-600">Complete guide to integrating NeoNoble Ramp API</p>
        </div>

        <Tabs defaultValue="quickstart" className="space-y-6">
          <TabsList>
            <TabsTrigger value="quickstart">Quick Start</TabsTrigger>
            <TabsTrigger value="authentication">Authentication</TabsTrigger>
            <TabsTrigger value="endpoints">API Endpoints</TabsTrigger>
            <TabsTrigger value="postman">Postman Examples</TabsTrigger>
          </TabsList>

          <TabsContent value="quickstart" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Quick Start Guide</CardTitle>
                <CardDescription>Get started with NeoNoble Ramp in minutes</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold text-lg mb-2">1. Create an API Key</h3>
                  <p className="text-gray-600 mb-2">Navigate to the API Keys section and create your first API key. You'll receive:</p>
                  <ul className="list-disc list-inside space-y-1 text-gray-600 ml-4">
                    <li><code className="bg-gray-100 px-2 py-0.5 rounded">API Key</code>: Used in X-API-KEY header</li>
                    <li><code className="bg-gray-100 px-2 py-0.5 rounded">API Secret</code>: Used to sign requests (keep secure!)</li>
                  </ul>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-2">2. Understanding NENO Pricing</h3>
                  <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                    <p className="font-medium text-indigo-900 mb-2">Fixed Price Model</p>
                    <ul className="space-y-1 text-indigo-800">
                      <li>• 1 NENO = 10,000 EUR</li>
                      <li>• Fee: 1% of transaction amount</li>
                      <li>• Chain: BSC (Binance Smart Chain)</li>
                    </ul>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-2">3. Make Your First Request</h3>
                  <p className="text-gray-600 mb-2">All Business API requests require HMAC authentication. See the Authentication tab for details.</p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="authentication" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>HMAC Authentication</CardTitle>
                <CardDescription>Secure your API requests with HMAC-SHA256 signatures</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold text-lg mb-2">Required Headers</h3>
                  <div className="bg-gray-50 rounded-lg p-4 space-y-2 font-mono text-sm">
                    <div><span className="text-indigo-600">X-API-KEY:</span> Your API key</div>
                    <div><span className="text-indigo-600">X-TIMESTAMP:</span> Current Unix timestamp in milliseconds</div>
                    <div><span className="text-indigo-600">X-SIGNATURE:</span> HMAC-SHA256 signature</div>
                    <div><span className="text-indigo-600">Content-Type:</span> application/json</div>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-2">Signature Calculation</h3>
                  <p className="text-gray-600 mb-3">The signature is calculated as:</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`signature = HMAC_SHA256(apiSecret, timestamp + bodyJson)

// Example (JavaScript with CryptoJS):
const timestamp = Date.now().toString();
const bodyJson = JSON.stringify(requestBody);
const message = timestamp + bodyJson;
const signature = CryptoJS.HmacSHA256(message, apiSecret).toString();`}
                    </pre>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-2">Important Notes</h3>
                  <ul className="list-disc list-inside space-y-1 text-gray-600 ml-4">
                    <li>Timestamp must be within ±5 minutes of server time</li>
                    <li>For GET requests with no body, use empty object: <code className="bg-gray-100 px-2 py-0.5 rounded">{}</code></li>
                    <li>bodyJson must be the raw JSON string sent in the request</li>
                    <li>Signature is hex-encoded HMAC-SHA256</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="endpoints" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Business API Endpoints</CardTitle>
                <CardDescription>All endpoints require HMAC authentication</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold text-lg mb-3">POST /api/ramp-api-onramp-quote</h3>
                  <p className="text-gray-600 mb-3">Get a quote for buying tokens with fiat</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`// Request
{
  "fromFiat": "EUR",
  "toToken": "NENO",
  "chain": "BSC",
  "amountFiat": 10000
}

// Response
{
  "amountFiat": 10000,
  "estimatedTokens": 1,
  "rate": 10000,
  "feeBase": 100,
  "token": "NENO",
  "chain": "BSC"
}`}
                    </pre>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">POST /api/ramp-api-onramp</h3>
                  <p className="text-gray-600 mb-3">Create an onramp session (buy tokens)</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`// Request
{
  "fromFiat": "EUR",
  "toToken": "NENO",
  "chain": "BSC",
  "amountFiat": 10000,
  "userWallet": "0x1234..."
}

// Response
{
  "sessionId": "NRAMP_1234567890_abc123",
  "status": "PENDING",
  "checkoutUrl": "https://neonoble.it/ramp/checkout/NRAMP_...",
  "details": {
    "type": "ONRAMP",
    "token": "NENO",
    "chain": "BSC",
    "amountFiat": 10000,
    "estimatedTokens": 1,
    "feeBase": 100,
    "rate": 10000
  }
}`}
                    </pre>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">POST /api/ramp-api-offramp-quote</h3>
                  <p className="text-gray-600 mb-3">Get a quote for selling tokens for fiat</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`// Request
{
  "token": "NENO",
  "chain": "BSC",
  "tokens": 1
}

// Response
{
  "tokens": 1,
  "amountFiat": 10000,
  "rate": 10000,
  "feeBase": 100
}`}
                    </pre>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">POST /api/ramp-api-offramp</h3>
                  <p className="text-gray-600 mb-3">Create an offramp session (sell tokens)</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`// Request
{
  "token": "NENO",
  "chain": "BSC",
  "tokens": 1,
  "userWallet": "0x1234...",
  "payoutDestination": "DE89370400440532013000"
}

// Response
{
  "sessionId": "NRAMP_1234567890_xyz789",
  "status": "PENDING",
  "checkoutUrl": "https://neonoble.it/ramp/checkout/NRAMP_...",
  "details": {
    "type": "OFFRAMP",
    "token": "NENO",
    "chain": "BSC",
    "tokens": 1,
    "amountFiat": 10000,
    "feeBase": 100,
    "rate": 10000,
    "payoutDestination": "DE89370400440532013000"
  }
}`}
                    </pre>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="postman" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Postman Setup</CardTitle>
                <CardDescription>Configure Postman for testing NeoNoble Ramp API</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold text-lg mb-3">Step 1: Create Environment Variables</h3>
                  <p className="text-gray-600 mb-3">In Postman, create these environment variables:</p>
                  <div className="bg-gray-50 rounded-lg p-4 space-y-2 font-mono text-sm">
                    <div><span className="text-indigo-600">API_KEY:</span> Your API key from the API Keys section</div>
                    <div><span className="text-indigo-600">API_SECRET:</span> Your API secret</div>
                    <div><span className="text-indigo-600">BASE_URL:</span> https://neonoble.it</div>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">Step 2: Pre-request Script</h3>
                  <p className="text-gray-600 mb-3">Add this script to your Postman request (Pre-request Script tab):</p>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm">
{`// Generate timestamp
const timestamp = Date.now().toString();
pm.environment.set("TIMESTAMP", timestamp);

// Get body
const bodyJson = pm.request.body.raw || "{}";

// Generate signature
const message = timestamp + bodyJson;
const signature = CryptoJS.HmacSHA256(
  message,
  pm.environment.get("API_SECRET")
).toString();

pm.environment.set("SIGNATURE", signature);`}
                    </pre>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">Step 3: Request Headers</h3>
                  <p className="text-gray-600 mb-3">Add these headers to your request:</p>
                  <div className="bg-gray-50 rounded-lg p-4 space-y-2 font-mono text-sm">
                    <div><span className="text-indigo-600">Content-Type:</span> application/json</div>
                    <div><span className="text-indigo-600">X-API-KEY:</span> {`{{API_KEY}}`}</div>
                    <div><span className="text-indigo-600">X-TIMESTAMP:</span> {`{{TIMESTAMP}}`}</div>
                    <div><span className="text-indigo-600">X-SIGNATURE:</span> {`{{SIGNATURE}}`}</div>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-lg mb-3">Example Request: Onramp Quote</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-600 mb-1">URL:</p>
                      <code className="bg-gray-100 px-3 py-2 rounded block text-sm">POST https://neonoble.it/api/ramp-api-onramp-quote</code>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">Body (JSON):</p>
                      <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                        <pre className="text-sm">
{`{
  "fromFiat": "EUR",
  "toToken": "NENO",
  "chain": "BSC",
  "amountFiat": 10000
}`}
                        </pre>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">Expected Response (1 NENO = 10,000 EUR):</p>
                      <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                        <pre className="text-sm">
{`{
  "amountFiat": 10000,
  "estimatedTokens": 1,
  "rate": 10000,
  "feeBase": 100,
  "token": "NENO",
  "chain": "BSC"
}`}
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
