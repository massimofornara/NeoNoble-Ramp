#!/usr/bin/env node
/**
 * Database initialization script
 * - Runs Prisma migrations
 * - Creates platform_internal API client
 * - Updates .env with API credentials
 */

const { PrismaClient } = require('@prisma/client');
const bcrypt = require('bcryptjs');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const prisma = new PrismaClient();

function generateApiKey() {
  const randomBytes = crypto.randomBytes(24);
  const key = randomBytes.toString('hex');
  return `NENO_${key}`;
}

function generateApiSecret() {
  const randomBytes = crypto.randomBytes(32);
  return randomBytes.toString('hex');
}

async function initDatabase() {
  try {
    console.log('🚀 Initializing NeoNoble Ramp database...');

    // Check if platform_internal already exists
    let platformClient = await prisma.apiClient.findFirst({
      where: { name: 'platform_internal' },
    });

    if (platformClient) {
      console.log('✅ platform_internal API client already exists');
      return;
    }

    console.log('📝 Creating platform_internal user...');

    // Create system user for platform_internal
    const systemEmail = 'system@neonoble.internal';
    let systemUser = await prisma.user.findUnique({
      where: { email: systemEmail },
    });

    if (!systemUser) {
      const randomPassword = generateApiSecret().substring(0, 16);
      const passwordHash = await bcrypt.hash(randomPassword, 10);

      systemUser = await prisma.user.create({
        data: {
          email: systemEmail,
          passwordHash,
          role: 'ADMIN',
        },
      });
      console.log('✅ System user created');
    }

    console.log('🔑 Generating platform_internal API credentials...');

    // Generate credentials
    const apiKey = generateApiKey();
    const apiSecret = generateApiSecret();

    // Create API client
    platformClient = await prisma.apiClient.create({
      data: {
        ownerId: systemUser.id,
        name: 'platform_internal',
        apiKey,
        apiSecret,
        status: 'ACTIVE',
        rateLimitDay: 999999, // High limit for internal use
      },
    });

    console.log('✅ platform_internal API client created');
    console.log('');
    console.log('API Key:', apiKey);
    console.log('API Secret:', apiSecret);
    console.log('');

    // Update .env file
    const envPath = path.join(__dirname, '..', '.env');
    let envContent = fs.readFileSync(envPath, 'utf8');

    // Replace or add NEONOBLE_PLATFORM_API_KEY
    if (envContent.includes('NEONOBLE_PLATFORM_API_KEY=')) {
      envContent = envContent.replace(
        /NEONOBLE_PLATFORM_API_KEY=".*"/,
        `NEONOBLE_PLATFORM_API_KEY="${apiKey}"`
      );
    } else {
      envContent += `\nNEONOBLE_PLATFORM_API_KEY="${apiKey}"`;
    }

    // Replace or add NEONOBLE_PLATFORM_API_SECRET
    if (envContent.includes('NEONOBLE_PLATFORM_API_SECRET=')) {
      envContent = envContent.replace(
        /NEONOBLE_PLATFORM_API_SECRET=".*"/,
        `NEONOBLE_PLATFORM_API_SECRET="${apiSecret}"`
      );
    } else {
      envContent += `\nNEONOBLE_PLATFORM_API_SECRET="${apiSecret}"`;
    }

    fs.writeFileSync(envPath, envContent);

    console.log('✅ .env file updated with platform credentials');
    console.log('🎉 Database initialization complete!');
    console.log('');
    console.log('Next steps:');
    console.log('1. Restart your Next.js server to load new environment variables');
    console.log('2. Access the Dev Portal at http://localhost:3000/dev/login');
    console.log('3. Access the User Ramp at http://localhost:3000/ramp');
  } catch (error) {
    console.error('❌ Database initialization failed:', error);
    throw error;
  } finally {
    await prisma.$disconnect();
  }
}

initDatabase()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });