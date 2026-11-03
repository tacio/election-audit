import marimo

__generated_with = "0.25.0"
app = marimo.App(width="full", app_title="Operations")


@app.cell
def _():
    import os

    import marimo as mo

    from election_audit.dashboard_data import AuditDataset
    from election_audit.dashboard_ui import controls, render_page, render_plot

    return AuditDataset, controls, mo, os, render_page, render_plot


@app.cell
def _(AuditDataset, mo, os):
    dataset_uri = os.environ.get("ELECTION_AUDIT_DATASET", "")
    mo.stop(
        not dataset_uri, mo.md("Set ELECTION_AUDIT_DATASET to a local or HTTPS dataset manifest.")
    )
    dataset = AuditDataset.open(dataset_uri)
    return (dataset,)


@app.cell
def _(dataset, mo):
    language = mo.ui.dropdown(
        options={"English": "en", "Português": "pt-BR"}, value="English", label="Language / Idioma"
    )
    language
    return (language,)


@app.cell
def _(dataset, language, mo):
    titles = {"en": "Operations", "pt-BR": "Operações"}
    mo.vstack(
        [
            mo.md("# " + titles[language.value]),
            mo.md(
                "[Coverage](./01_coverage) · [Electoral](./02_electoral) · [Operations](./03_operations) · [Models](./04_models)"
            ),
            mo.md(
                "**Release:** `"
                + dataset.manifest["release_id"]
                + "` · **Access:** `"
                + dataset.manifest["access_state"]
                + "`"
            ),
            mo.md("\n\n".join(dataset.manifest.get("notes", []))),
        ]
    )
    return


@app.cell
def _(controls, dataset, language, mo):
    available = {
        "coverage": ["coverage", "reconciliation", "hierarchy"],
        "electoral": ["electoral", "unanimity", "rounds", "features"],
        "operations": ["operations", "late", "timing", "features"],
        "models": ["models", "features", "impact"],
    }["operations"]
    tables = [name for name in available if name in dataset.tables]
    mo.stop(
        not tables,
        mo.md(
            "No eligible data published for this page / Nenhum dado elegível publicado para esta página."
        ),
    )
    table = mo.ui.dropdown(options=tables, value=tables[0], label="Table / Tabela")
    table
    return (table,)


@app.cell
def _(controls, dataset, language, mo, table):
    filter_controls = controls(dataset, table.value, language.value)
    filter_controls
    return (filter_controls,)


@app.cell
def _(dataset, filter_controls, mo, render_page, table):
    selected_filters = {key: value for key, value in filter_controls.value.items() if key != "page"}
    result = dataset.page(
        table.value, filters=selected_filters, offset=int(filter_controls.value["page"]) * 250
    )
    render_page(dataset, result, mo)
    return result, selected_filters


@app.cell
def _(mo, result):
    from election_audit.dashboard_ui import numeric_fields

    measures = numeric_fields(result["rows"])
    mo.stop(
        not measures,
        mo.md(
            "No eligible numeric measure in this selection / Nenhuma medida numérica elegível nesta seleção."
        ),
    )
    measure = mo.ui.dropdown(options=measures, value=measures[0], label="Measure / Medida")
    measure
    return (measure,)


@app.cell
def _(measure, mo, render_plot, result):
    render_plot(result["rows"], measure.value, mo, {k: v for k, v in result.items() if k != "rows"})
    return


if __name__ == "__main__":
    app.run()
