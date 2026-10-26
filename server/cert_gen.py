"""
Self-signed SSL certificate generator with Subject Alternative Names (SAN).
Generates certificates valid for localhost, 127.0.0.1, and all active LAN IP addresses
so mobile browsers (Chrome / Firefox on Android) permit navigator.mediaDevices.getUserMedia.
"""

import os
import socket
import ipaddress
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def get_local_ip_addresses():
    """Discover all non-loopback IPv4 addresses on the host."""
    ips = set(["127.0.0.1"])
    try:
        # Standard UDP socket trick to find the preferred outbound LAN interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    return sorted(list(ips))

def _cert_covers_ips(cert_path: Path, required_ips: list[str]) -> bool:
    """Verify existing certificate is unexpired and includes all current local IPs in SAN."""
    try:
        cert_bytes = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_bytes)
        now = datetime.datetime.now(datetime.timezone.utc)
        if now < cert.not_valid_before_utc or now >= cert.not_valid_after_utc:
            return False

        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        cert_ips = {str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)}
        for ip_str in required_ips:
            if ip_str not in cert_ips:
                return False
        return True
    except Exception:
        return False


def ensure_ssl_certificates(cert_dir: Path):
    """
    Ensure valid SSL cert.pem and key.pem exist in cert_dir.
    If missing, expired, or missing a current LAN IP in SAN, generate a new RSA 2048 key and X.509 cert.
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    local_ips = get_local_ip_addresses()

    if cert_path.exists() and key_path.exists() and _cert_covers_ips(cert_path, local_ips):
        return str(cert_path), str(key_path)

    # Generate RSA private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"LiveAirMic M4L"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"liveairmic.local"),
    ])

    san_entries = [
        x509.DNSName(u"localhost"),
        x509.DNSName(u"liveairmic.local"),
    ]
    for ip_str in local_ips:
        try:
            san_entries.append(x509.IPAddress(ipaddress.IPv4Address(ip_str)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=730)) # 2 years
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Write private key
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return str(cert_path), str(key_path)

if __name__ == "__main__":
    certs_dir = Path(__file__).resolve().parent.parent / ".certs"
    c, k = ensure_ssl_certificates(certs_dir)
    print(f"Generated certificates:\n  Cert: {c}\n  Key:  {k}")
