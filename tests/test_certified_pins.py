import json
import re
import unittest
from importlib.resources import files

PIN = files("election_audit").joinpath("resources/pins/certified-manifests-2026.json")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class CertifiedPinTests(unittest.TestCase):
    def test_both_rounds_are_pinned_by_distinct_digests(self):
        pins = json.loads(PIN.read_text())
        self.assertEqual(set(pins["rounds"]), {"1", "2"})
        digests = []
        for pin in pins["rounds"].values():
            for key in ("manifest_sha256", "certificate_sha256", "staging_certificate_sha256"):
                self.assertRegex(pin[key], DIGEST)
                digests.append(pin[key])
            self.assertGreater(pin["objects"], 0)
        self.assertEqual(len(digests), len(set(digests)))


if __name__ == "__main__":
    unittest.main()
