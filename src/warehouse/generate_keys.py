from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_keys():

    # Generate RSA private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Export private key in PKCS8 PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Export public key in PEM format
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Save keys in project root
    Path("snowflake_private_key.p8").write_bytes(private_pem)

    Path("snowflake_public_key.pub").write_bytes(public_pem)

    print("RSA keys generated successfully!")

    print("Private key: snowflake_private_key.p8")
    print("Public key: snowflake_public_key.pub")


if __name__ == "__main__":
    generate_rsa_keys()
