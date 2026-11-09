"""xr1 triage: does ed521.verify accept a signature under the identity (small-order) key?"""

from election_audit import ed521

identity = ed521.encode((0, 1, 1, 0))
base = ed521.encode(ed521.BASE) if hasattr(ed521, "BASE") else None
forged = base + (1).to_bytes(ed521.SIZE, "little")
for message in (b"any message", b"another"):
    print("identity key, R=B, S=1:", message, ed521.verify(identity, forged, message))
