import os
import base64
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """Get the AES-256 encryption key from environment."""
    key_hex = os.environ.get('API_SECRET_ENCRYPTION_KEY')
    if not key_hex:
        raise ValueError(
            "API_SECRET_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    try:
        key_bytes = bytes.fromhex(key_hex)
        if len(key_bytes) != 32:
            raise ValueError(f"Key must be 32 bytes (256 bits), got {len(key_bytes)} bytes")
        return key_bytes
    except Exception as e:
        raise ValueError(f"Invalid encryption key format: {e}")


def generate_api_key() -> str:
    """Generate a unique API key (public identifier)."""
    return f"nn_live_{secrets.token_hex(16)}"


def generate_api_secret() -> str:
    """Generate a secure API secret."""
    return secrets.token_hex(32)


def encrypt_secret(plaintext: str) -> tuple[str, str, str]:
    """Encrypt an API secret using AES-256-GCM.
    
    Returns:
        Tuple of (encrypted_data_base64, iv_base64, auth_tag_base64)
    """
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    
    # Generate a random 96-bit IV (recommended for GCM)
    iv = secrets.token_bytes(12)
    
    # Encrypt the secret
    plaintext_bytes = plaintext.encode('utf-8')
    ciphertext = aesgcm.encrypt(iv, plaintext_bytes, None)
    
    # GCM appends the auth tag (16 bytes) to the ciphertext
    # Split them for storage
    encrypted_data = ciphertext[:-16]
    auth_tag = ciphertext[-16:]
    
    return (
        base64.b64encode(encrypted_data).decode('utf-8'),
        base64.b64encode(iv).decode('utf-8'),
        base64.b64encode(auth_tag).decode('utf-8')
    )


def decrypt_secret(encrypted_data_b64: str, iv_b64: str, auth_tag_b64: str) -> str:
    """Decrypt an API secret using AES-256-GCM.
    
    Args:
        encrypted_data_b64: Base64 encoded encrypted data
        iv_b64: Base64 encoded initialization vector
        auth_tag_b64: Base64 encoded authentication tag
    
    Returns:
        Decrypted plaintext secret
    """
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    
    encrypted_data = base64.b64decode(encrypted_data_b64)
    iv = base64.b64decode(iv_b64)
    auth_tag = base64.b64decode(auth_tag_b64)
    
    # GCM expects ciphertext + auth_tag concatenated
    ciphertext = encrypted_data + auth_tag
    
    plaintext_bytes = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext_bytes.decode('utf-8')
