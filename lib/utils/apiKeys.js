import crypto from 'crypto';

/**
 * Generate a unique API key with NENO_ prefix
 * @returns {string} API key
 */
export function generateApiKey() {
  const randomBytes = crypto.randomBytes(24);
  const key = randomBytes.toString('hex');
  return `NENO_${key}`;
}

/**
 * Generate a cryptographically secure API secret
 * @returns {string} API secret
 */
export function generateApiSecret() {
  const randomBytes = crypto.randomBytes(32);
  return randomBytes.toString('hex');
}