import base64, hashlib, json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from app.services.receipt_service import _canonical


def test_canonical_is_deterministic():
    a = {"b": 1, "a": 2, "c": [3, 1, 2]}
    assert _canonical(a) == _canonical({"c": [3, 1, 2], "a": 2, "b": 1})


def test_signature_roundtrip_and_tamper():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    body = {"receipt_version": "tracememory.receipt/v1", "trace_id": "t1", "x": [1, 2, 3]}
    encoded = _canonical(body)
    sig = key.sign(encoded)
    pub = key.public_key()
    # valid
    pub.verify(sig, encoded)
    # tampered body -> signature must fail
    tampered = _canonical({**body, "x": [1, 2, 4]})
    with pytest.raises(Exception):
        pub.verify(sig, tampered)


def test_hash_matches_canonical():
    body = {"a": 1, "b": "two"}
    h = hashlib.sha256(_canonical(body)).hexdigest()
    assert h == hashlib.sha256(_canonical({"b": "two", "a": 1})).hexdigest()
