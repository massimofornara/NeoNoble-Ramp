-- CreateEnum
CREATE TYPE "UserRole" AS ENUM ('USER', 'ADMIN');

-- CreateEnum
CREATE TYPE "ApiClientStatus" AS ENUM ('ACTIVE', 'DISABLED');

-- CreateEnum
CREATE TYPE "RampSessionType" AS ENUM ('ONRAMP', 'OFFRAMP');

-- CreateEnum
CREATE TYPE "RampSessionStatus" AS ENUM ('PENDING', 'AWAITING_PAYMENT', 'PROCESSING', 'PAYMENT_CONFIRMED', 'CHAIN_PENDING', 'CHAIN_CONFIRMED', 'COMPLETED', 'FAILED', 'REFUNDED');

-- CreateEnum
CREATE TYPE "PlatformApiKeyStatus" AS ENUM ('ACTIVE', 'REVOKED', 'EXPIRED');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "role" "UserRole" NOT NULL DEFAULT 'USER',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ApiClient" (
    "id" TEXT NOT NULL,
    "ownerId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "apiKey" TEXT NOT NULL,
    "apiSecret" TEXT NOT NULL,
    "status" "ApiClientStatus" NOT NULL DEFAULT 'ACTIVE',
    "rateLimitDay" INTEGER NOT NULL DEFAULT 1000,
    "totalCalls" INTEGER NOT NULL DEFAULT 0,
    "totalFeeBase" DECIMAL(20,2) NOT NULL DEFAULT 0,
    "lastResetAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "dailyCalls" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastUsedAt" TIMESTAMP(3),

    CONSTRAINT "ApiClient_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ApiCallLog" (
    "id" TEXT NOT NULL,
    "apiClientId" TEXT,
    "endpoint" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "statusCode" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "extraMeta" JSONB,

    CONSTRAINT "ApiCallLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RampSession" (
    "id" TEXT NOT NULL,
    "apiClientId" TEXT NOT NULL,
    "type" "RampSessionType" NOT NULL,
    "tokenSymbol" TEXT NOT NULL,
    "chain" TEXT NOT NULL,
    "amountFiat" DECIMAL(20,2) NOT NULL,
    "tokens" DECIMAL(30,18) NOT NULL,
    "feeBase" DECIMAL(20,2) NOT NULL,
    "status" "RampSessionStatus" NOT NULL DEFAULT 'PENDING',
    "checkoutUrl" TEXT NOT NULL,
    "userWallet" TEXT,
    "payoutDestination" TEXT,
    "paymentProvider" TEXT,
    "paymentSessionId" TEXT,
    "paymentIntentId" TEXT,
    "paymentStatus" TEXT,
    "txHash" TEXT,
    "txStatus" TEXT,
    "blockNumber" INTEGER,
    "gasUsed" TEXT,
    "errorMessage" TEXT,
    "retryCount" INTEGER NOT NULL DEFAULT 0,
    "lastProcessedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "RampSession_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Nonce" (
    "id" TEXT NOT NULL,
    "apiClientId" TEXT NOT NULL,
    "nonce" TEXT NOT NULL,
    "timestamp" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Nonce_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WebhookEvent" (
    "id" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "eventId" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "processed" BOOLEAN NOT NULL DEFAULT false,
    "rampSessionId" TEXT,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processedAt" TIMESTAMP(3),

    CONSTRAINT "WebhookEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PlatformApiKey" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "apiKey" TEXT NOT NULL,
    "secretHash" TEXT NOT NULL,
    "status" "PlatformApiKeyStatus" NOT NULL DEFAULT 'ACTIVE',
    "rateLimitDay" INTEGER NOT NULL DEFAULT 10000,
    "dailyCalls" INTEGER NOT NULL DEFAULT 0,
    "totalCalls" INTEGER NOT NULL DEFAULT 0,
    "lastResetAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "description" TEXT,
    "allowedIps" TEXT,
    "metadata" JSONB,
    "createdBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastUsedAt" TIMESTAMP(3),
    "revokedAt" TIMESTAMP(3),
    "revokedBy" TEXT,

    CONSTRAINT "PlatformApiKey_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE INDEX "User_email_idx" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "ApiClient_apiKey_key" ON "ApiClient"("apiKey");

-- CreateIndex
CREATE INDEX "ApiClient_apiKey_idx" ON "ApiClient"("apiKey");

-- CreateIndex
CREATE INDEX "ApiClient_ownerId_idx" ON "ApiClient"("ownerId");

-- CreateIndex
CREATE INDEX "ApiCallLog_apiClientId_idx" ON "ApiCallLog"("apiClientId");

-- CreateIndex
CREATE INDEX "ApiCallLog_createdAt_idx" ON "ApiCallLog"("createdAt");

-- CreateIndex
CREATE INDEX "RampSession_apiClientId_idx" ON "RampSession"("apiClientId");

-- CreateIndex
CREATE INDEX "RampSession_status_idx" ON "RampSession"("status");

-- CreateIndex
CREATE INDEX "RampSession_createdAt_idx" ON "RampSession"("createdAt");

-- CreateIndex
CREATE INDEX "RampSession_paymentSessionId_idx" ON "RampSession"("paymentSessionId");

-- CreateIndex
CREATE INDEX "RampSession_txHash_idx" ON "RampSession"("txHash");

-- CreateIndex
CREATE INDEX "Nonce_expiresAt_idx" ON "Nonce"("expiresAt");

-- CreateIndex
CREATE UNIQUE INDEX "Nonce_apiClientId_nonce_key" ON "Nonce"("apiClientId", "nonce");

-- CreateIndex
CREATE UNIQUE INDEX "WebhookEvent_eventId_key" ON "WebhookEvent"("eventId");

-- CreateIndex
CREATE INDEX "WebhookEvent_provider_eventType_idx" ON "WebhookEvent"("provider", "eventType");

-- CreateIndex
CREATE INDEX "WebhookEvent_processed_idx" ON "WebhookEvent"("processed");

-- CreateIndex
CREATE INDEX "WebhookEvent_createdAt_idx" ON "WebhookEvent"("createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "PlatformApiKey_apiKey_key" ON "PlatformApiKey"("apiKey");

-- CreateIndex
CREATE INDEX "PlatformApiKey_apiKey_idx" ON "PlatformApiKey"("apiKey");

-- CreateIndex
CREATE INDEX "PlatformApiKey_status_idx" ON "PlatformApiKey"("status");

-- CreateIndex
CREATE INDEX "PlatformApiKey_createdAt_idx" ON "PlatformApiKey"("createdAt");

-- AddForeignKey
ALTER TABLE "ApiClient" ADD CONSTRAINT "ApiClient_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RampSession" ADD CONSTRAINT "RampSession_apiClientId_fkey" FOREIGN KEY ("apiClientId") REFERENCES "ApiClient"("id") ON DELETE CASCADE ON UPDATE CASCADE;
