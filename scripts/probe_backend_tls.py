#!/usr/bin/env python3
"""Capture the current public TLS 1.2 chain without sending HTTP or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).absolute().parent.parent
OPENSSL = "/usr/bin/openssl"
CA_FILE = "/etc/ssl/cert.pem"
PEM = re.compile(rb"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
PROFILES = {"default": None, "ecdsa_aes": "ECDHE-ECDSA-AES128-GCM-SHA256",
            "rsa_aes": "ECDHE-RSA-AES128-GCM-SHA256"}


def endpoint_host(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("invalid_endpoint")
    value = json.loads(path.read_text(encoding="utf-8")).get("base_url")
    if type(value) is not str or not value.isascii() or len(value) > 240:
        raise ValueError("invalid_endpoint")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com", host)):
        raise ValueError("invalid_endpoint")
    return host


def private_write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)


def probe(live=False, profile="default"):
    if not live:
        return {"status": "not_requested"}
    if profile not in PROFILES:
        raise ValueError("invalid_profile")
    host = endpoint_host(ROOT / "private/service/endpoint.json")
    if not Path(OPENSSL).is_file() or not Path(CA_FILE).is_file():
        return {"status": "tls_tools_missing"}
    folder = ROOT / "private/board-baseline"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    # LibreSSL on this Mac has no -verify_hostname; check the authenticated leaf
    # locally with Python's hostname verifier after OpenSSL verifies its chain.
    command = [OPENSSL, "s_client", "-connect", host + ":443", "-servername", host,
               "-tls1_2", "-showcerts", "-verify", "8",
               "-CAfile", CA_FILE, "-no_ign_eof"]
    if profile == "default":
        command.append("-verify_return_error")
    else:
        # Diagnostic-only handshakes retain a rejected peer chain for inspection.
        # OpenSSL still reports verification; no application bytes are sent.
        command += ["-cipher", PROFILES[profile]]
    prefix = "backend" if profile == "default" else "backend-" + profile
    timed_out = False
    try:
        result = subprocess.run(command, input=b"", capture_output=True, timeout=20, check=False)
        output, errors, returncode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        output, errors, returncode = exc.stdout or b"", exc.stderr or b"", None
        timed_out = True
    private_write(folder / (prefix + "-tls.log"), output + b"\n" + errors)
    certificates = PEM.findall(output)
    # Export only complete PEM certificates, never the TLS session-key log.
    private_write(folder / (prefix + "-chain.pem"), b"\n".join(certificates) + (b"\n" if certificates else b""))
    der = [ssl.PEM_cert_to_DER_cert(pem.decode("ascii")) for pem in certificates]
    hashes = [hashlib.sha256(certificate).hexdigest() for certificate in der]
    chain_verified = returncode == 0 and b"Verify return code: 0 (ok)" in output
    hostname_verified = False
    if certificates:
        leaf = folder / (prefix + "-leaf.pem")
        private_write(leaf, certificates[0] + b"\n")
        try:
            ssl.match_hostname(ssl._ssl._test_decode_cert(str(leaf)), host)
            hostname_verified = True
        except (ssl.SSLError, ValueError):
            pass
    verified = chain_verified and hostname_verified
    return {"status": "captured_verified" if verified else "capture_timeout" if timed_out else
                       "captured_unverified" if certificates else "tls_probe_failed",
            "profile": profile, "certificate_count": len(certificates), "certificate_sha256": hashes,
            "certificate_bytes": [len(certificate) for certificate in der],
            "chain_verified": chain_verified, "hostname_verified": hostname_verified,
            "http_sent": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Perform the requested TLS diagnostics; never send HTTP")
    parser.add_argument("--compare-aes", action="store_true",
                        help="Compare two fixed AES cipher handshakes, up to 20 seconds each; save unverified chains as diagnostics")
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        return
    try:
        result = [probe(live=True, profile=name) for name in ("ecdsa_aes", "rsa_aes")] if args.compare_aes else probe(live=True)
    except Exception:
        result = {"status": "tls_probe_error", "http_sent": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
