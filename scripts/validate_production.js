#!/usr/bin/env node
/**
 * Production Environment Validation Script
 * Validates all critical components before launch
 * 
 * Run: node scripts/validate_production.js
 */

const { PrismaClient } = require('@prisma/client');
const https = require('https');
const { isBlockchainConfigured, getWalletBalance } = require('../lib/services/blockchainService');

const prisma = new PrismaClient();

const REQUIRED_ENV_VARS = [
  'DATABASE_URL',
  'JWT_SECRET',
  'NEXT_PUBLIC_BASE_URL',
  'NEONOBLE_PLATFORM_API_KEY',
  'NEONOBLE_PLATFORM_API_SECRET',
];

const CONDITIONAL_ENV_VARS = {
  payment: ['STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET'],
  blockchain: ['BSC_RPC_URL', 'BSC_PRIVATE_KEY', 'NENO_CONTRACT_ADDRESS'],
};

class ProductionValidator {
  constructor() {
    this.results = {
      passed: [],
      warnings: [],
      failed: [],
    };
  }

  /**
   * Run all validation checks
   */
  async validate() {
    console.log('🔍 NeoNoble Ramp - Production Validation');
    console.log('='.repeat(60));
    console.log('');

    await this.checkEnvironmentVariables();
    await this.checkDatabaseConnectivity();
    await this.checkDatabaseSchema();
    await this.checkPlatformClient();
    await this.checkPaymentConfiguration();
    await this.checkBlockchainConfiguration();
    await this.checkWebhookReachability();
    await this.printSummary();

    const hasCriticalFailures = this.results.failed.length > 0;
    
    if (hasCriticalFailures) {
      console.log('');
      console.log('❌ VALIDATION FAILED - Do not deploy to production');
      process.exit(1);
    } else if (this.results.warnings.length > 0) {
      console.log('');
      console.log('⚠️  VALIDATION PASSED WITH WARNINGS');
      process.exit(0);
    } else {
      console.log('');
      console.log('✅ VALIDATION PASSED - Ready for production');
      process.exit(0);
    }
  }

  /**
   * Check environment variables
   */
  async checkEnvironmentVariables() {
    console.log('📋 Checking environment variables...');

    // Required vars
    for (const envVar of REQUIRED_ENV_VARS) {
      if (process.env[envVar]) {
        this.pass(`${envVar} is set`);
      } else {
        this.fail(`${envVar} is missing`);
      }
    }

    // Payment vars (conditional)
    const paymentMode = process.env.PAYMENT_MODE;
    if (paymentMode === 'live') {
      for (const envVar of CONDITIONAL_ENV_VARS.payment) {
        if (process.env[envVar]) {
          this.pass(`${envVar} is set (payment mode: live)`);
        } else {
          this.fail(`${envVar} is missing (required for live payment mode)`);
        }
      }
    } else {
      this.warn(`PAYMENT_MODE is '${paymentMode}' (not live)`);
    }

    // Blockchain vars
    for (const envVar of CONDITIONAL_ENV_VARS.blockchain) {
      if (process.env[envVar]) {
        this.pass(`${envVar} is set`);
      } else {
        this.warn(`${envVar} is missing (blockchain features disabled)`);
      }
    }

    console.log('');
  }

  /**
   * Check database connectivity
   */
  async checkDatabaseConnectivity() {
    console.log('🗄️  Checking database connectivity...');

    try {
      await prisma.$connect();
      this.pass('Database connection successful');
      
      // Test query
      await prisma.user.findFirst();
      this.pass('Database queries working');
    } catch (error) {
      this.fail(`Database connection failed: ${error.message}`);
    }

    console.log('');
  }

  /**
   * Check database schema
   */
  async checkDatabaseSchema() {
    console.log('📊 Checking database schema...');

    try {
      // Check if all required tables exist
      const tables = ['User', 'ApiClient', 'ApiCallLog', 'RampSession', 'Nonce', 'WebhookEvent'];
      
      for (const table of tables) {
        try {
          await prisma[table.charAt(0).toLowerCase() + table.slice(1)].findFirst();
          this.pass(`Table '${table}' exists`);
        } catch (error) {
          this.fail(`Table '${table}' missing or inaccessible`);
        }
      }
    } catch (error) {
      this.fail(`Schema validation failed: ${error.message}`);
    }

    console.log('');
  }

  /**
   * Check platform_internal client
   */
  async checkPlatformClient() {
    console.log('🔑 Checking platform_internal client...');

    try {
      const platformClient = await prisma.apiClient.findFirst({
        where: { name: 'platform_internal' },
      });

      if (platformClient) {
        this.pass('platform_internal client exists');
        
        if (platformClient.status === 'ACTIVE') {
          this.pass('platform_internal client is ACTIVE');
        } else {
          this.fail('platform_internal client is not ACTIVE');
        }

        if (process.env.NEONOBLE_PLATFORM_API_KEY === platformClient.apiKey) {
          this.pass('Platform API key matches environment');
        } else {
          this.fail('Platform API key mismatch');
        }
      } else {
        this.fail('platform_internal client not found');
      }
    } catch (error) {
      this.fail(`Platform client check failed: ${error.message}`);
    }

    console.log('');
  }

  /**
   * Check payment configuration
   */
  async checkPaymentConfiguration() {
    console.log('💳 Checking payment configuration...');

    const paymentMode = process.env.PAYMENT_MODE || 'mock';
    console.log(`   Payment mode: ${paymentMode}`);

    if (paymentMode === 'live') {
      if (process.env.STRIPE_SECRET_KEY && process.env.STRIPE_SECRET_KEY.startsWith('sk_live_')) {
        this.pass('Stripe live key detected');
      } else if (process.env.STRIPE_SECRET_KEY && process.env.STRIPE_SECRET_KEY.startsWith('sk_test_')) {
        this.warn('Stripe test key detected (not for production)');
      } else {
        this.fail('Invalid Stripe secret key');
      }
    } else {
      this.warn('Payment mode is mock (not for production)');
    }

    console.log('');
  }

  /**
   * Check blockchain configuration
   */
  async checkBlockchainConfiguration() {
    console.log('⛓️  Checking blockchain configuration...');

    if (!isBlockchainConfigured()) {
      this.warn('Blockchain not configured');
      console.log('');
      return;
    }

    try {
      const balance = await getWalletBalance();
      this.pass(`Wallet balance: ${balance} NENO`);

      const balanceNum = parseFloat(balance);
      if (balanceNum < 1) {
        this.warn('Wallet balance is low (< 1 NENO)');
      } else if (balanceNum < 10) {
        this.warn('Wallet balance is moderate (< 10 NENO)');
      } else {
        this.pass('Wallet balance is sufficient');
      }
    } catch (error) {
      this.fail(`Blockchain check failed: ${error.message}`);
    }

    console.log('');
  }

  /**
   * Check webhook reachability (if deployed)
   */
  async checkWebhookReachability() {
    console.log('🔗 Checking webhook endpoint...');

    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL;
    
    if (!baseUrl || baseUrl.includes('localhost')) {
      this.warn('Base URL is localhost (webhooks will not work)');
      console.log('');
      return;
    }

    const webhookUrl = `${baseUrl}/api/webhooks/stripe`;
    console.log(`   Testing: ${webhookUrl}`);

    try {
      const response = await this.testEndpoint(webhookUrl);
      if (response.statusCode === 400 || response.statusCode === 405) {
        // Expected - endpoint exists but requires POST
        this.pass('Webhook endpoint is reachable');
      } else {
        this.warn(`Webhook returned unexpected status: ${response.statusCode}`);
      }
    } catch (error) {
      this.fail(`Webhook endpoint not reachable: ${error.message}`);
    }

    console.log('');
  }

  /**
   * Test HTTP endpoint
   */
  testEndpoint(url) {
    return new Promise((resolve, reject) => {
      const req = https.get(url, (res) => {
        resolve({ statusCode: res.statusCode });
      });

      req.on('error', reject);
      req.setTimeout(5000, () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });
    });
  }

  /**
   * Print summary
   */
  async printSummary() {
    console.log('='.repeat(60));
    console.log('📊 VALIDATION SUMMARY');
    console.log('='.repeat(60));
    console.log(`✅ Passed: ${this.results.passed.length}`);
    console.log(`⚠️  Warnings: ${this.results.warnings.length}`);
    console.log(`❌ Failed: ${this.results.failed.length}`);
    console.log('');

    if (this.results.warnings.length > 0) {
      console.log('⚠️  WARNINGS:');
      this.results.warnings.forEach((w) => console.log(`   - ${w}`));
      console.log('');
    }

    if (this.results.failed.length > 0) {
      console.log('❌ FAILURES:');
      this.results.failed.forEach((f) => console.log(`   - ${f}`));
      console.log('');
    }
  }

  pass(message) {
    this.results.passed.push(message);
    console.log(`   ✅ ${message}`);
  }

  warn(message) {
    this.results.warnings.push(message);
    console.log(`   ⚠️  ${message}`);
  }

  fail(message) {
    this.results.failed.push(message);
    console.log(`   ❌ ${message}`);
  }
}

// Run validation
const validator = new ProductionValidator();
validator.validate().catch((error) => {
  console.error('Fatal validation error:', error);
  process.exit(1);
});