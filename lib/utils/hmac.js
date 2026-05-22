import crypto from 'crypto';

/**
 * Sign a request using HMAC-SHA256
 * @param {string} apiSecret - The API secret key
 * @param {string} timestamp - Unix timestamp in milliseconds
 * @param {string} bodyJson - JSON string of the request body
 * @returns {string} Hex-encoded HMAC signature
 */
export function signRequest(apiSecret, timestamp, bodyJson) {
  const message = timestamp + bodyJson;
  const hmac = crypto.createHmac('sha256', apiSecret);
  hmac.update(message);
  return hmac.digest('hex');
}

/**
 * Verify a request signature
 * @param {string} apiSecret - The API secret key
 * @param {string} timestamp - Unix timestamp in milliseconds
 * @param {string} bodyJson - JSON string of the request body
 * @param {string} signature - The signature to verify
 * @returns {boolean} True if signature is valid
 */
export function verifySignature(apiSecret, timestamp, bodyJson, signature) {
  const expectedSignature = signRequest(apiSecret, timestamp, bodyJson);
  return crypto.timingSafeEqual(
    Buffer.from(expectedSignature),
    Buffer.from(signature)
  );
}