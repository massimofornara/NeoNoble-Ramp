CREATE TABLE "Transaction" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "fromToken" TEXT,
    "toToken" TEXT,
    "cryptoAmount" TEXT,
    "fiatAmount" TEXT,
    "fiatCurrency" TEXT,
    "network" TEXT NOT NULL,
    "txHash" TEXT,
    "step" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Transaction_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "Transaction_userId_createdAt_idx" ON "Transaction"("userId", "createdAt");
CREATE INDEX "Transaction_status_updatedAt_idx" ON "Transaction"("status", "updatedAt");
CREATE INDEX "Transaction_type_status_idx" ON "Transaction"("type", "status");
CREATE INDEX "Transaction_txHash_idx" ON "Transaction"("txHash");
