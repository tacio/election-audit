# Packet P3: cryptography and signed artifacts

Scope:

- `election_audit/ed521.py`
- `election_audit/ed521_crosscheck.py`
- `election_audit/urn_pki.py`
- `election_audit/electoral_verification.py`
- `election_audit/signed_results.py`
- `election_audit/hash_lists.py`
- `election_audit/resources/*.asn1`, `resources/pki/` and `resources/pins/`.
- Their tests.
- `docs/en/integrity-checks.md`: the sections on Ed521, certificates, hash lists and JWS.

Press on:

- Ed521: is verification strict where it must be (point decoding, cofactor, scalar
  range, non-canonical encodings)? Can a malleated signature pass?
- Certificate chains and revocation: can an expired, revoked, wrong-issuer or
  self-signed certificate be accepted? Is "not consulted" ever reported as a pass?
- What exactly does each signature cover? Can bytes that the analysis reads lie outside
  the signed content?
- JWS: algorithm confusion, a key taken from the token itself, payload canonicalization.
- Where do the pinned keys and certificates come from, and could the pin be circular
  (verifying data with a key taken from the same data)?
