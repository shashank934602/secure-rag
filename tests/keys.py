"""Throwaway RS256 key pairs for tests (spec 09 D5): generated once per test run, never stored."""

from functools import cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import TokenKeys


def pem_pair(name: str = "test") -> tuple[bytes, bytes]:
    """(private PEM, public PEM); `name` gives distinct pairs (e.g. "attacker", "old")."""
    return _pair(name)  # one cache key per name, however it's called


@cache
def _pair(name: str) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, public


def token_keys(name: str = "test") -> TokenKeys:
    private, public = pem_pair(name)
    return TokenKeys.from_pems(private, public)


KEYS = token_keys()
