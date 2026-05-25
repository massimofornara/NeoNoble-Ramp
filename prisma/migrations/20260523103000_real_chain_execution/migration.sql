ALTER TABLE "Transaction"
  ADD COLUMN "blockNumber" INTEGER,
  ADD COLUMN "gasUsed" TEXT,
  ADD COLUMN "confirmations" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "chainStatus" TEXT,
  ADD COLUMN "rawTxData" JSONB,
  ADD COLUMN "fromAddress" TEXT,
  ADD COLUMN "toAddress" TEXT,
  ADD COLUMN "settlementId" TEXT,
  ADD COLUMN "paymentReference" TEXT,
  ADD COLUMN "errorMessage" TEXT;

CREATE INDEX "Transaction_chainStatus_idx" ON "Transaction"("chainStatus");
CREATE INDEX "Transaction_settlementId_idx" ON "Transaction"("settlementId");

CREATE TABLE "TransactionEvent" (
    "id" TEXT NOT NULL,
    "transactionId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "payload" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TransactionEvent_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "TransactionEvent_transactionId_createdAt_idx" ON "TransactionEvent"("transactionId", "createdAt");
CREATE INDEX "TransactionEvent_eventType_createdAt_idx" ON "TransactionEvent"("eventType", "createdAt");

ALTER TABLE "TransactionEvent"
  ADD CONSTRAINT "TransactionEvent_transactionId_fkey"
  FOREIGN KEY ("transactionId") REFERENCES "Transaction"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;
