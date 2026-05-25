ALTER TABLE "Transaction"
ADD COLUMN IF NOT EXISTS "executionAttempts" JSONB,
ADD COLUMN IF NOT EXISTS "fallbackPath" JSONB,
ADD COLUMN IF NOT EXISTS "lastSuccessfulRail" TEXT;

CREATE INDEX IF NOT EXISTS "Transaction_lastSuccessfulRail_idx" ON "Transaction"("lastSuccessfulRail");
