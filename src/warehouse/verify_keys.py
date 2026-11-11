import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

load_dotenv()

key_path = Path(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"))

with open(key_path, "rb") as key_file:
    private_key = serialization.load_pem_private_key(key_file.read(), password=None)

public_key_der = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
)

fingerprint = base64.b64encode(hashlib.sha256(public_key_der).digest()).decode("utf-8")

print("Private key loaded successfully")
print("Expected Snowflake fingerprint:")
print(f"SHA256:{fingerprint}")
