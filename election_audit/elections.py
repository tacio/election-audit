"""Validated presidential election identities, independent of storage names.

2026 is the audited election and the default everywhere. 2022 is the negative control
(analysis plan section 7.6); its rounds are known so its logs can be read with their own
reviewed rules.
"""

from dataclasses import asdict, dataclass
from typing import Any

# (year, round) -> (pleito, election, election date)
ELECTIONS = {
    (2026, 1): ("3220", "6257", "2026-10-04"),
    (2026, 2): ("3221", "6258", "2026-10-25"),
    (2022, 1): ("406", "544", "2022-10-02"),
    (2022, 2): ("407", "545", "2022-10-30"),
}


@dataclass(frozen=True)
class ElectionDescriptor:
    year: int
    pleito_code: str
    election_code: str
    round: int
    election_date: str

    def __post_init__(self) -> None:
        key = (self.year, self.round)
        if type(self.round) is not int or type(self.year) is not int or key not in ELECTIONS:
            raise ValueError("Only 2026 and 2022 presidential rounds 1 and 2 are supported")
        if (self.pleito_code, self.election_code, self.election_date) != ELECTIONS[key]:
            raise ValueError("Election descriptor identifiers/date disagree")

    @property
    def phase(self) -> str:
        return "o"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def election_for_round(round_number: int = 2, year: int = 2026) -> ElectionDescriptor:
    if type(round_number) is not int or round_number not in (1, 2):
        raise ValueError("Round must be 1 or 2")
    if (year, round_number) not in ELECTIONS:
        raise ValueError(f"Unsupported election year: {year!r}")
    pleito, election, date = ELECTIONS[(year, round_number)]
    return ElectionDescriptor(year, pleito, election, round_number, date)


def coerce_election(value: ElectionDescriptor | dict[str, Any] | None = None) -> ElectionDescriptor:
    if value is None:
        return election_for_round()
    if isinstance(value, ElectionDescriptor):
        return value
    if isinstance(value, dict):
        try:
            return ElectionDescriptor(**value)
        except TypeError as exc:
            raise ValueError("Invalid election descriptor fields") from exc
    raise ValueError("Expected an election descriptor")
