import hmac
import hashlib
import time
import logging

logger = logging.getLogger(__name__)

# Timestamp window for replay protection (5 minutes in seconds)
TIMESTAMP_WINDOW = 300


def generate_hmac_signature(timestamp: str, body_json: str, api_secret: str) -> str:
    """Generate HMAC-SHA256 signature.
    
    Signature = HMAC-SHA256(timestamp + bodyJson, apiSecret)
    """
    message = f"{timestamp}{body_json}"
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def verify_hmac_signature(
    provided_signature: str,
    timestamp: str,
    body_json: str,
    api_secret: str
) -> bool:
    """Verify HMAC signature with constant-time comparison."""
    expected_signature = generate_hmac_signature(timestamp, body_json, api_secret)
    return hmac.compare_digest(provided_signature, expected_signature)


def validate_timestamp(timestamp: str) -> tuple[bool, str]:
    """Validate timestamp is within acceptable window for replay protection.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        diff = abs(current_time - request_time)
        
        if diff > TIMESTAMP_WINDOW:
            return False, f"Timestamp outside acceptable window. Difference: {diff}s, Max allowed: {TIMESTAMP_WINDOW}s"
        
        return True, ""
    except ValueError:
        return False, "Invalid timestamp format. Expected Unix timestamp in seconds."
