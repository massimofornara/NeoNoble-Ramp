import crypto from 'crypto';

// Encryption key from environment (REQUIRED - must be 32 bytes for AES-256)
const getEncryptionKey = () => {
  const key = process.env.API_SECRET_ENCRYPTION_KEY;
  
  if (!key) {
    throw new Error(
      'CRITICAL: API_SECRET_ENCRYPTION_KEY environment variable is missing!\n' +
      'Generate one with: openssl rand -hex 32\n' +
      'Add to .env: API_SECRET_ENCRYPTION_KEY=<generated_key>'
    );
  }
  
  if (key.length !== 64) {
    throw new Error(
      `CRITICAL: API_SECRET_ENCRYPTION_KEY must be 64 hex characters (32 bytes)!\n` +
      `Current length: ${key.length}\n` +
      `Generate a new one with: openssl rand -hex 32`
    );
  }
  
  return Buffer.from(key, 'hex');
};

let ENCRYPTION_KEY;
try {
  ENCRYPTION_KEY = getEncryptionKey();
} catch (error) {
  console.error(error.message);
  throw error;
}

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const AUTH_TAG_LENGTH = 16;

/**
 * Encrypt a secret for secure storage
 */
export function encryptSecret(secret) {
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, ENCRYPTION_KEY, iv);
  
  let encrypted = cipher.update(secret, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  
  const authTag = cipher.getAuthTag();
  
  // Return: iv:authTag:encrypted
  return `${iv.toString('hex')}:${authTag.toString('hex')}:${encrypted}`;
}

/**
 * Decrypt a secret from storage
 */
export function decryptSecret(encryptedData) {
  try {
    const parts = encryptedData.split(':');
    if (parts.length !== 3) {
      throw new Error('Invalid encrypted data format');
    }
    
    const [ivHex, authTagHex, encrypted] = parts;
    const iv = Buffer.from(ivHex, 'hex');
    const authTag = Buffer.from(authTagHex, 'hex');
    
    const decipher = crypto.createDecipheriv(ALGORITHM, ENCRYPTION_KEY, iv);
    decipher.setAuthTag(authTag);
    
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  } catch (error) {
    console.error('Failed to decrypt secret:', error);
    throw new Error('Decryption failed');
  }
}

/**
 * Hash a secret using SHA-256 (for comparison, not for HMAC)
 */
export function hashSecret(secret) {
  return crypto.createHash('sha256').update(secret).digest('hex');
}
