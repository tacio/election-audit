"""Type aliases shared across modules.

Values decoded from JSON, ASN.1 or Parquet rows are plain dicts whose shape is fixed by the
producing stage, not by a class; these aliases name that shape without claiming more.
"""

from collections.abc import Sequence
from typing import Any

type JSON = dict[str, Any]
"""A decoded JSON object, ASN.1 structure or manifest."""

type Row = dict[str, Any]
"""One output or query row, column name to value."""

type Argv = Sequence[str] | None
"""Arguments of a ``*_main`` entry point; None reads ``sys.argv``."""
