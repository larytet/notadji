"""Reference helpers built on the `cryptography` package."""
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.poly1305 import Poly1305


def le(b):
    return int.from_bytes(bytes(b), "little")


def keystream(key, nonce12, counter, n=64):
    c = Cipher(algorithms.ChaCha20(bytes(key), counter.to_bytes(4, "little") + bytes(nonce12)), mode=None).encryptor()
    return c.update(b"\x00" * n)


def seal(key, nonce, aad, pt):
    ct_tag = ChaCha20Poly1305(bytes(key)).encrypt(bytes(nonce), bytes(pt), bytes(aad))
    return list(aad) + list(ct_tag)           # AAD || ciphertext || tag


def poly_tag(key32, msg):
    return Poly1305.generate_tag(bytes(key32), bytes(msg))


CLAMP = 0x0ffffffc0ffffffc0ffffffc0fffffff
