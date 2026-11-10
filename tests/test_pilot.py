"""Pilot review exports only date tokens (xr1-20261109-P6-02)."""

import unittest

from election_audit.pilot import DATE_TOKEN


class DateTokenTests(unittest.TestCase):
    def test_only_valid_dates_are_exported(self) -> None:
        self.assertTrue(DATE_TOKEN.fullmatch("04/10/2026"))
        for token in ("1234567890", "AB12CD34EF", "32/10/2026", "04/13/2026", "04-10-2026"):
            self.assertIsNone(DATE_TOKEN.fullmatch(token), token)


if __name__ == "__main__":
    unittest.main()
