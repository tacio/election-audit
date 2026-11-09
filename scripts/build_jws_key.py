"""Extract TSE's official JWS key and certificates from its verification manual (appendix B).

Usage: python -I scripts/build_jws_key.py manual-verificacao-jws.pdf key.json

Needs poppler's ``pdftotext``. The pinned key file (``signed_results.PINNED_KEY_FILES``) was
built with pdftotext 24.02.0 from the manual of 16 September 2026 (SHA-256 ``db114514…``);
another pdftotext version may lay the text out differently, so compare the JWK and the
three certificates, not only the file digest. Moved into the repository from the frozen
input folder ``tse-jws-key-20261108`` (xr1-20261109-P8-10); the logic is unchanged.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

URL = (
    "https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/"
    "divulgacao-de-resultados/manual-verificacao-jws"
)


def build(pdf: Path, out: Path) -> None:
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    official = text.split("Apêndice B: Chaves e certificados OFICIAIS")[1]
    found = re.search(r"\{[^{}]*\"kty\"[^{}]*\}", official)
    if found is None:
        raise SystemExit("No JWK in appendix B")
    jwk = json.loads(found.group(0))
    pems = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", official, re.S)
    if len(pems) != 3:
        raise SystemExit(f"Expected 3 certificates, found {len(pems)}")
    pems = ["\n".join(line.strip() for line in p.splitlines()) + "\n" for p in pems]
    key = {
        "jwk": jwk,
        "certificates": dict(zip(("end_entity", "intermediate", "root"), pems, strict=True)),
        "source": {
            "document": "manual-verificacao-jws.pdf (Apêndice B: Chaves e certificados OFICIAIS)",
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "url": URL,
            "dated": "2026-09-16",
            "extracted_with": "pdftotext -layout; JWK and the three PEM blocks after 'Apêndice B'",
        },
    }
    if out.exists():
        raise SystemExit(f"Output must be new: {out}")
    out.write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
