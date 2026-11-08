"""Shared notebook controls and bounded visualizations; computations stay in the pipeline."""

from __future__ import annotations

import math
from typing import Any

from election_audit.dashboard_data import AuditDataset
from election_audit.types import JSON, Row


def controls(dataset: AuditDataset, table: str, language: str = "en") -> Any:
    import marimo as mo

    from election_audit.dashboard_data import DIMENSIONS

    labels = {
        "uf": "UF",
        "municipality_tse": "Municipality / Município",
        "zone": "Zone / Zona",
        "round": "Round / Turno",
        "readiness": "Readiness / Prontidão",
        "location_id": "Location / Local",
    }
    widgets: dict[str, Any] = {
        key: mo.ui.dropdown(
            options=["all", *dataset.options(table, key)],
            value="all",
            label=labels.get(key, key.replace("_", " ").title()),
        )
        for key in DIMENSIONS
    }
    widgets["page"] = mo.ui.number(
        start=0, stop=1000000, step=1, value=0, label="Page / Página (250 rows)"
    )
    return mo.ui.dictionary(widgets)


def render_page(dataset: AuditDataset, result: JSON, mo: Any) -> Any:
    csv, metadata = dataset.csv(
        result["table"], filters=result["filters"], offset=result["offset"], limit=result["limit"]
    )
    import json

    count = len(result["rows"])
    return mo.vstack(
        [
            mo.md(
                f"**Population / População:** {result['total']:,} matching records · showing {count:,} from offset {result['offset']:,}. Charts use this page only. Unknown values are never zero."
            ),
            mo.ui.table(result["rows"], pagination=True, page_size=25, selection=None),
            mo.hstack(
                [
                    mo.download(
                        csv.encode(), filename=result["table"] + ".csv", label="Download page CSV"
                    ),
                    mo.download(
                        json.dumps(metadata, indent=2).encode(),
                        filename="selection.json",
                        label="Download provenance",
                    ),
                ]
            ),
            mo.md(
                "Anonymous cycles cannot be attributed to candidates. Statistical ranks are descriptive unless a validated inferential interpretation is explicitly recorded."
            ),
        ]
    )


def _flat(row: JSON, prefix: str = "") -> dict[str, float]:
    result = {}
    for key, value in row.items():
        name = prefix + key
        if isinstance(value, dict):
            result.update(_flat(value, name + "."))
        elif type(value) in (int, float) and math.isfinite(value):
            result[name] = value
    return result


def numeric_fields(rows: list[Row]) -> list[str]:
    fields = {key for row in rows for key in _flat(row)}
    preferred = [
        "turnout",
        "observed",
        "value",
        "signed_residual",
        "observed_completed_cycles",
        "units",
    ]
    return [key for key in preferred if key in fields] + sorted(fields - set(preferred))


def render_plot(rows: list[Row], measure: str, mo: Any, provenance: JSON | None = None) -> Any:
    import altair as alt

    values = [
        {"record": i, "value": _flat(row)[measure], "uf": row.get("uf", "unknown")}
        for i, row in enumerate(rows)
        if measure in _flat(row)
    ]
    if not values:
        return mo.md("Measure unavailable / Medida indisponível")
    histogram = (
        alt.Chart(alt.Data(values=values))  # ty: ignore[unresolved-attribute]  # mark_* hides the type
        .mark_bar()
        .encode(
            x=alt.X("value:Q", bin=alt.Bin(maxbins=30), title=measure),
            y=alt.Y("count():Q", title="Records in page"),
            tooltip=[alt.Tooltip("count():Q")],
        )
        .properties(height=280)
    )
    points = (
        alt.Chart(alt.Data(values=values))  # ty: ignore[unresolved-attribute]  # mark_* hides the type
        .mark_circle(size=45, opacity=0.6)
        .encode(
            x="record:Q",
            y=alt.Y("value:Q", title=measure),
            color="uf:N",
            tooltip=["record:Q", "value:Q", "uf:N"],
        )
        .properties(height=280)
    )
    charts = mo.ui.altair_chart(histogram | points)
    coordinates = [
        {"latitude": r["latitude"], "longitude": r["longitude"], "value": _flat(r).get(measure)}
        for r in rows
        if type(r.get("latitude")) in (int, float)
        and type(r.get("longitude")) in (int, float)
        and -90 <= r["latitude"] <= 90
        and -180 <= r["longitude"] <= 180
    ]
    map_view = (
        mo.ui.altair_chart(
            alt.Chart(alt.Data(values=coordinates))  # ty: ignore[unresolved-attribute]  # mark_* hides the type
            .mark_circle()
            .encode(
                latitude="latitude:Q", longitude="longitude:Q", color="value:Q", tooltip=["value:Q"]
            )
            .project("mercator")
            .properties(height=300)
        )
        if coordinates
        else mo.md(
            "Map unavailable: no verified coordinates in this page / Mapa indisponível: sem coordenadas verificadas nesta página."
        )
    )
    import json

    artifact = (histogram | points).to_dict()
    artifact["usermeta"] = provenance or {}
    return mo.vstack(
        [
            charts,
            map_view,
            mo.download(
                json.dumps(artifact).encode(),
                filename="chart.vl.json",
                label="Download chart with provenance",
            ),
        ]
    )
