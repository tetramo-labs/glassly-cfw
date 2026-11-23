"""Strict offline .dat inspection. Does not talk to devices or guess ciphers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_crypto():
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    path = ROOT / "third_party/8cryptdo/cryptdo8.py"
    if sha256(path.read_bytes()) != lock["cryptdo8"]["sha256"]:
        raise ValueError("8cryptdo source hash mismatch")
    spec = importlib.util.spec_from_file_location("cryptdo8", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_sections(raw):
    if not raw:
        raise ValueError("Empty firmware image")
    sections, offset = [], 0
    while offset < len(raw):
        if len(raw) - offset < 28:
            raise ValueError(f"Truncated header/trailing bytes at {offset:#x}")
        version, address, size, pid = struct.unpack_from("<4I", raw, offset)
        if not size or size % 512 or size > len(raw) - offset - 28:
            raise ValueError(f"Invalid payload size at {offset:#x}")
        if raw[offset + 16:offset + 28] != bytes(12):
            raise ValueError(f"Unsupported nonzero reserved header at {offset:#x}")
        sections.append(dict(offset=offset, id=version, addr=address,
                             payload_len=size, pid=pid))
        offset += 28 + size
    return sections


def unpack(raw, ciphers):
    crypto = load_crypto()
    sections = parse_sections(raw)
    if len(sections) != len(ciphers):
        raise ValueError("One explicit cipher is required for every section")
    payloads, rebuilt = [], bytearray()
    for section, name in zip(sections, ciphers):
        cipher = crypto.CIPHERS[name]
        if section["payload_len"] > cipher.MAX_BLOCKS * 512:
            raise ValueError("Payload exceeds cipher key schedule")
        payload = crypto.decrypt_section(raw, section, cipher)
        if len(payload) != section["payload_len"]:
            raise ValueError("Incomplete decryption")
        rebuilt.extend(crypto.build_section(payload, cipher, section["id"],
                                           section["addr"], len(payload), section["pid"]))
        payloads.append(payload)
    if bytes(rebuilt) != raw:
        raise ValueError("Byte-exact container roundtrip failed")
    return sections, payloads


def load_stock():
    lock = json.loads((ROOT / "sources.lock.json").read_text())["stock"]
    raw = (ROOT / lock["path"]).read_bytes()
    if len(raw) != lock["size"] or sha256(raw) != lock["sha256"]:
        raise ValueError("Stock package does not match pinned v1.08")
    sections, payloads = unpack(raw, [s["cipher"] for s in lock["sections"]])
    for actual, expected, payload in zip(sections, lock["sections"], payloads):
        if any(actual[k] != expected[k] for k in actual):
            raise ValueError("Section header mismatch")
        if sha256(payload) != expected["sha256"]:
            raise ValueError("Section plaintext hash mismatch")
    return raw, sections, payloads
