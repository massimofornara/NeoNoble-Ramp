ALTER TABLE "Transaction"
  ADD COLUMN "chainId" INTEGER,
  ADD COLUMN "chainName" TEXT,
  ADD COLUMN "finalityStatus" TEXT,
  ADD COLUMN "settlementLayer" TEXT;

UPDATE "Transaction"
SET
  "chainId" = CASE
    WHEN upper("network") = 'ETHEREUM' THEN 1
    WHEN upper("network") = 'ARBITRUM' THEN 42161
    WHEN upper("network") = 'OPTIMISM' THEN 10
    WHEN upper("network") = 'ZKSYNC' THEN 324
    ELSE 56
  END,
  "chainName" = CASE
    WHEN upper("network") = 'ETHEREUM' THEN 'Ethereum'
    WHEN upper("network") = 'ARBITRUM' THEN 'Arbitrum'
    WHEN upper("network") = 'OPTIMISM' THEN 'Optimism'
    WHEN upper("network") = 'ZKSYNC' THEN 'zkSync'
    ELSE 'BSC'
  END,
  "finalityStatus" = CASE
    WHEN "chainStatus" = 'finalized' THEN 'finalized'
    WHEN "chainStatus" = 'confirmed' THEN 'confirmed'
    WHEN "chainStatus" = 'invalid_chain_tx' THEN 'invalid'
    ELSE COALESCE("chainStatus", 'unknown')
  END,
  "settlementLayer" = CASE
    WHEN upper("network") IN ('ETHEREUM', 'ARBITRUM', 'OPTIMISM', 'ZKSYNC') THEN lower("network")
    ELSE 'bsc'
  END
WHERE "chainId" IS NULL;

CREATE INDEX "Transaction_chainId_chainStatus_idx" ON "Transaction"("chainId", "chainStatus");
CREATE INDEX "Transaction_finalityStatus_idx" ON "Transaction"("finalityStatus");
