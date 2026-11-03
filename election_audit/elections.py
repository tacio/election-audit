"""Validated 2026 presidential election identities, independent of storage names."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ElectionDescriptor:
    year: int
    pleito_code: str
    election_code: str
    round: int
    election_date: str

    def __post_init__(self):
        expected = {1: ("3220", "6257", "2026-10-04"), 2: ("3221", "6258", "2026-10-25")}
        if type(self.round) is not int or self.year != 2026 or self.round not in expected:
            raise ValueError("Only 2026 presidential rounds 1 and 2 are supported")
        if (self.pleito_code, self.election_code, self.election_date) != expected[self.round]:
            raise ValueError("Election descriptor identifiers/date disagree")

    @property
    def phase(self):
        return "o"

    def as_dict(self):
        return asdict(self)


def election_for_round(round_number=2):
    if type(round_number) is not int or round_number not in (1, 2):
        raise ValueError("Round must be 1 or 2")
    pleito, election, date = {1: ("3220", "6257", "2026-10-04"), 2: ("3221", "6258", "2026-10-25")}[
        round_number
    ]
    return ElectionDescriptor(2026, pleito, election, round_number, date)


def coerce_election(value=None):
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
