#!/usr/bin/env node
/**
 * Load Testing Script for NeoNoble Ramp
 * Simulates concurrent onramp and offramp transactions
 * 
 * Run: node scripts/load_test.js
 */

const axios = require('axios');
const crypto = require('crypto');
const { signRequest } = require('../lib/utils/hmac');

const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3000';
const API_KEY = process.env.TEST_API_KEY || '';
const API_SECRET = process.env.TEST_API_SECRET || '';
const CONCURRENT_REQUESTS = parseInt(process.env.LOAD_TEST_CONCURRENCY || '10', 10);
const TOTAL_REQUESTS = parseInt(process.env.LOAD_TEST_TOTAL || '100', 10);

class LoadTester {
  constructor() {
    this.results = {
      total: 0,
      success: 0,
      failed: 0,
      latencies: [],
      errors: {},
    };
  }

  /**
   * Run load test
   */
  async run() {
    console.log('🚀 NeoNoble Ramp - Load Testing');
    console.log('='.repeat(60));
    console.log(`Base URL: ${BASE_URL}`);
    console.log(`Concurrent requests: ${CONCURRENT_REQUESTS}`);
    console.log(`Total requests: ${TOTAL_REQUESTS}`);
    console.log('');

    if (!API_KEY || !API_SECRET) {
      console.error('❌ TEST_API_KEY and TEST_API_SECRET must be set');
      process.exit(1);
    }

    const startTime = Date.now();

    // Run tests in batches
    const batches = Math.ceil(TOTAL_REQUESTS / CONCURRENT_REQUESTS);
    
    for (let batch = 0; batch < batches; batch++) {
      const batchSize = Math.min(CONCURRENT_REQUESTS, TOTAL_REQUESTS - (batch * CONCURRENT_REQUESTS));
      console.log(`Running batch ${batch + 1}/${batches} (${batchSize} requests)...`);
      
      const promises = [];
      
      for (let i = 0; i < batchSize; i++) {
        // Alternate between onramp and offramp
        if (Math.random() > 0.5) {
          promises.push(this.testOnrampQuote());
        } else {
          promises.push(this.testOfframpQuote());
        }
      }
      
      await Promise.allSettled(promises);
    }

    const totalTime = Date.now() - startTime;

    this.printResults(totalTime);
  }

  /**
   * Test onramp quote endpoint
   */
  async testOnrampQuote() {
    const startTime = Date.now();
    this.results.total++;

    try {
      const body = {
        fromFiat: 'EUR',
        toToken: 'NENO',
        chain: 'BSC',
        amountFiat: Math.floor(Math.random() * 50000) + 1000,
      };

      const response = await this.makeAuthenticatedRequest(
        'POST',
        '/api/ramp-api-onramp-quote',
        body
      );

      const latency = Date.now() - startTime;
      this.results.latencies.push(latency);

      if (response.status === 200) {
        this.results.success++;
      } else {
        this.results.failed++;
        this.recordError(response.status, response.data?.error);
      }
    } catch (error) {
      this.results.failed++;
      this.recordError('EXCEPTION', error.message);
    }
  }

  /**
   * Test offramp quote endpoint
   */
  async testOfframpQuote() {
    const startTime = Date.now();
    this.results.total++;

    try {
      const body = {
        token: 'NENO',
        chain: 'BSC',
        tokens: (Math.random() * 5).toFixed(6),
      };

      const response = await this.makeAuthenticatedRequest(
        'POST',
        '/api/ramp-api-offramp-quote',
        body
      );

      const latency = Date.now() - startTime;
      this.results.latencies.push(latency);

      if (response.status === 200) {
        this.results.success++;
      } else {
        this.results.failed++;
        this.recordError(response.status, response.data?.error);
      }
    } catch (error) {
      this.results.failed++;
      this.recordError('EXCEPTION', error.message);
    }
  }

  /**
   * Make authenticated request with HMAC
   */
  async makeAuthenticatedRequest(method, endpoint, body) {
    const timestamp = Date.now().toString();
    const bodyJson = JSON.stringify(body);
    const signature = signRequest(API_SECRET, timestamp, bodyJson);

    try {
      const response = await axios({
        method,
        url: `${BASE_URL}${endpoint}`,
        data: body,
        headers: {
          'Content-Type': 'application/json',
          'X-API-KEY': API_KEY,
          'X-TIMESTAMP': timestamp,
          'X-SIGNATURE': signature,
        },
        validateStatus: () => true, // Don't throw on any status
        timeout: 10000,
      });

      return response;
    } catch (error) {
      return {
        status: 0,
        data: { error: error.message },
      };
    }
  }

  /**
   * Record error
   */
  recordError(type, message) {
    const key = `${type}: ${message}`;
    this.results.errors[key] = (this.results.errors[key] || 0) + 1;
  }

  /**
   * Calculate statistics
   */
  calculateStats() {
    if (this.results.latencies.length === 0) {
      return { avg: 0, min: 0, max: 0, p50: 0, p95: 0, p99: 0 };
    }

    const sorted = [...this.results.latencies].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);

    return {
      avg: Math.round(sum / sorted.length),
      min: sorted[0],
      max: sorted[sorted.length - 1],
      p50: sorted[Math.floor(sorted.length * 0.5)],
      p95: sorted[Math.floor(sorted.length * 0.95)],
      p99: sorted[Math.floor(sorted.length * 0.99)],
    };
  }

  /**
   * Print results
   */
  printResults(totalTime) {
    console.log('');
    console.log('='.repeat(60));
    console.log('📊 LOAD TEST RESULTS');
    console.log('='.repeat(60));
    console.log('');

    const stats = this.calculateStats();
    const throughput = Math.round((this.results.total / totalTime) * 1000);

    console.log('📈 Summary:');
    console.log(`   Total requests: ${this.results.total}`);
    console.log(`   Successful: ${this.results.success}`);
    console.log(`   Failed: ${this.results.failed}`);
    console.log(`   Success rate: ${((this.results.success / this.results.total) * 100).toFixed(2)}%`);
    console.log(`   Total time: ${(totalTime / 1000).toFixed(2)}s`);
    console.log(`   Throughput: ${throughput} req/s`);
    console.log('');

    console.log('⏱️  Latency (ms):');
    console.log(`   Average: ${stats.avg}ms`);
    console.log(`   Min: ${stats.min}ms`);
    console.log(`   Max: ${stats.max}ms`);
    console.log(`   P50: ${stats.p50}ms`);
    console.log(`   P95: ${stats.p95}ms`);
    console.log(`   P99: ${stats.p99}ms`);
    console.log('');

    if (Object.keys(this.results.errors).length > 0) {
      console.log('❌ Errors:');
      Object.entries(this.results.errors)
        .sort((a, b) => b[1] - a[1])
        .forEach(([error, count]) => {
          console.log(`   ${error}: ${count}`);
        });
      console.log('');
    }

    // Pass/fail determination
    const successRate = (this.results.success / this.results.total) * 100;
    
    if (successRate >= 95 && stats.p95 < 1000) {
      console.log('✅ LOAD TEST PASSED');
      process.exit(0);
    } else if (successRate >= 90) {
      console.log('⚠️  LOAD TEST PASSED WITH WARNINGS');
      process.exit(0);
    } else {
      console.log('❌ LOAD TEST FAILED');
      process.exit(1);
    }
  }
}

// Install axios if not present
try {
  require.resolve('axios');
} catch (e) {
  console.error('❌ axios not installed. Run: yarn add axios');
  process.exit(1);
}

// Run load test
const tester = new LoadTester();
tester.run().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});