"""Build, validate, bounded read-only query and bilingual initial report interfaces."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from election_audit.archive_parsing import _read_checked
from election_audit.publication import (
    PublicationError,
    ResourceConfig,
    _table_summary,
    _validate,
    _validate_accounting,
    build_from_parse,
    build_from_snapshot,
    inspect_release,
    open_release,
    publish_release,
    resolve_release,
)
from election_audit.source_inventory import digest
from election_audit.types import JSON, Argv

COUNT_SQL = "SELECT completion_state, count(*) AS observed_cycles FROM anonymous_cycle GROUP BY completion_state ORDER BY completion_state"
LATE_SQL = "SELECT count(*) AS sessions, count(try_cast(json_extract_string(payload, '$.completed_cycles_after17') AS BIGINT)) AS classifiable_sessions FROM late_voting"
LIFECYCLE_SQL = "SELECT event_kind, sum(json_extract(payload, '$.normalized_event_count')::BIGINT) AS normalized_events FROM processing_event_availability GROUP BY event_kind ORDER BY event_kind"


def validate_release(path: Path, *, _verified_document: JSON | None = None) -> JSON:
    """Rehash all bytes, recompute logical rows and verify relational/accounting rules."""
    path = resolve_release(path)
    document = _verified_document if _verified_document is not None else inspect_release(path)
    if document["identity"]["version"] == "derivative-release-v1":
        from election_audit.derivatives import validate_derivative

        return validate_derivative(path, document)
    context = _read_checked(path, "context.json")
    if digest(context) != document["identity"]["parse_id"]:
        raise PublicationError("Frozen context provenance mismatch")
    with open_release(path, _verified_document=document) as connection:
        names = sorted(document["tables"])
        deferred = _validate(connection, names)
        _validate_accounting(connection, context, set(document["selected_objects"]))
        for name, spec in document["tables"].items():
            actual = _table_summary(connection, name)
            if any(actual[key] != spec[key] for key in actual):
                raise PublicationError(f"Logical digest/accounting mismatch: {name}")
    expected = {r["object_sha256"] for r in context["artifacts"]}
    if not set(document["selected_objects"]) <= expected:
        raise PublicationError("Selected object partition is outside frozen context")
    if deferred != document["deferred_checks"]:
        raise PublicationError("Deferred check manifest mismatch")
    config = ResourceConfig(**document["settings_applied"])
    if document["identity"]["config"] != document["settings_applied"]:
        raise PublicationError("Resource provenance mismatch")
    return {
        "release_id": path.name,
        "integrity": "passed",
        "grains_foreign_keys": "passed",
        "accounting_lineage": "passed_for_available_inputs",
        "logical_digests": "passed",
        "deferred_checks": deferred,
        "metadata_lineage_state": document["metadata_lineage_state"],
        "resource_limits": config.__dict__,
        "national_status": "partial_national",
        "selected_objects": len(document["selected_objects"]),
        "expected_objects": len(expected),
        "electoral_validation": "unavailable",
        "cross_shard_overlap": document["cross_shard_overlap"],
    }


def _restrict_query(connection: duckdb.DuckDBPyConnection, path: Path, document: JSON) -> None:
    from election_audit.derivatives import allowed_fact_paths

    files = allowed_fact_paths(path, document)
    connection.execute("SET allowed_paths=?", [files])
    connection.execute("SET enable_external_access=false")
    connection.execute("SET lock_configuration=true")


def _query_connection(connection: duckdb.DuckDBPyConnection, sql: str, max_rows: int) -> JSON:
    statements = connection.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise PublicationError("Queries require exactly one SELECT statement")
    cursor = connection.execute(sql)
    rows = cursor.fetchmany(max_rows + 1)
    return {
        "columns": [field[0] for field in cursor.description],
        "rows": rows[:max_rows],
        "truncated": len(rows) > max_rows,
        "max_rows": max_rows,
    }


def query_release(path: Path, sql: str, *, max_rows: int = 1000) -> JSON:
    """One full integrity pass, one parsed SELECT, bounded output, no external access."""
    if type(max_rows) is not int or not 1 <= max_rows <= 100_000:
        raise PublicationError("Query row limit must be between 1 and 100000")
    path = resolve_release(path)
    document = inspect_release(path)
    with open_release(path, _verified_document=document) as connection:
        if "test_partition_status" in document.get("combined_tables", {}):
            from election_audit.analysis import protect_test_query

            protect_test_query(connection, document, sql)
        _restrict_query(connection, path, document)
        return _query_connection(connection, sql, max_rows)


def _findings(path: Path, output: Path, document: JSON) -> JSON:
    context = _read_checked(path, "context.json")
    with open_release(path, _verified_document=document) as connection:
        _restrict_query(connection, path, document)
        cycles = _query_connection(connection, COUNT_SQL, 1000)
        lifecycle = _query_connection(connection, LIFECYCLE_SQL, 1000)
        late = _query_connection(connection, LATE_SQL, 1000)
    return {
        "release_id": path.name,
        "national_status": "partial_national",
        "expected_members": context["coverage_summary"].get("expected_members"),
        "declared_ufs": context["coverage_summary"].get("declared_ufs", []),
        "denominator_scope": "full_frozen_indexes_of_declared_UFs_only",
        "retained_members": document["tables"]["operational_coverage"]["rows"],
        "selected_objects": len(document["selected_objects"]),
        "expected_objects": document["expected_objects"],
        "observed_sessions": document["tables"]["voting_session"]["rows"],
        "observed_cycle_states": cycles["rows"],
        "global_eligible_cycle_total": None,
        "normalized_lifecycle_events": lifecycle["rows"],
        "late_voting_availability": late["rows"],
        "cross_shard_overlap": document["cross_shard_overlap"],
        "metadata_lineage_state": document["metadata_lineage_state"],
        "electoral_validation": "unavailable",
        "calculations": {
            "cycles": COUNT_SQL,
            "lifecycle": LIFECYCLE_SQL,
            "late_availability": LATE_SQL,
            "late_boundary": "completion_at > target_date 17:00:00 America/Sao_Paulo",
            "late_share": "completed_cycles_after17 / classifiable_completed_cycles",
        },
        "finding_evidence": [
            {
                "id": "coverage",
                "inputs": ["operational_coverage", "context.coverage_summary"],
                "calculation": "count(distinct section_id); expected_members from frozen index",
                "assumption": "frozen_expected_index_only",
                "exclusions": "outside_declared_ufs_and_unselected_content",
                "uncertainty": "partial_national_unknown_strata",
                "challenging_evidence": "authoritative_index_or_composition_changes",
                "reproduce": f"rtk proxy env UV_OFFLINE=1 just validate '{path}'",
            },
            {
                "id": "cycles",
                "inputs": ["anonymous_cycle", "record_lineage", "session_summaries"],
                "calculation": COUNT_SQL,
                "assumption": "reviewed_session_semantics",
                "exclusions": "unresolved_official_selection",
                "uncertainty": "cross_shard_copy_overlap_and_missing_blocks",
                "challenging_evidence": "line_hashes_copy_claims_and_parser_issues",
                "reproduce": f"rtk proxy env UV_OFFLINE=1 just query '{path}' --sql '{COUNT_SQL}'",
            },
            {
                "id": "lifecycle",
                "inputs": ["processing_event_availability"],
                "calculation": LIFECYCLE_SQL,
                "assumption": "event_kind_and_supported_timezone_separate",
                "exclusions": "download_http_headers_not_publisher_events",
                "uncertainty": "publisher_feed_unavailable",
                "challenging_evidence": "authoritative_original_lifecycle_records",
                "reproduce": f"rtk proxy env UV_OFFLINE=1 just query '{path}' --sql-file {shlex.quote(str(output / 'lifecycle.sql'))}",
            },
            {
                "id": "late_voting",
                "inputs": [
                    "late_voting",
                    "selected_event",
                    "anonymous_cycle",
                    "election",
                    "section",
                ],
                "calculation": "completion_at > target_date 17:00:00 America/Sao_Paulo",
                "assumption": "supported_domestic_clocks_and_official_context",
                "exclusions": "overseas_unvalidated_convention",
                "uncertainty": "bounded_clock_sensitivity_and_unknown_lifecycle",
                "challenging_evidence": "reviewed_clock_bounds_opening_closing_and_copy_evidence",
                "reproduce": f"rtk proxy env UV_OFFLINE=1 just query '{path}' --sql-file {shlex.quote(str(output / 'late.sql'))}",
            },
        ],
        "inputs": {
            "parse_id": document["identity"]["parse_id"],
            "shards": document["identity"]["shards"],
        },
    }


TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "title": "Initial operational report",
        "scope": "Partial national corpus: available AC–RJ 2026 presidential runoff logs. Frozen subsets retain the full indexed denominator; this report does not establish national completeness.",
        "labels": [
            "Declared frozen UFs (full-UF denominator scope)",
            "Expected indexed members",
            "Retained members",
            "Selected content objects",
            "Frozen parsed content objects",
            "Observed reconstructed sessions",
            "Observed cycle states",
            "Global eligible cycle total",
            "Normalized lifecycle events",
            "Cross-shard overlap",
            "Metadata lineage",
            "Electoral validation",
            "Late-voting availability (sessions, classifiable sessions)",
        ],
        "unknown": "unavailable / unknown",
        "inputs": "Inputs and calculation",
        "assumptions": "Assumptions and exclusions",
        "uncertainty": "Uncertainty and challenging evidence",
        "reproduce": "Reproduce",
        "body": "Counts use unique content events and reconstructed anonymous cycles. They are not reconciled electoral votes. Package/member/lineage witnesses do not multiply these facts. Session selection, clocks and copied histories require reviewed source evidence. Receipt, processing, generation, publication and client observation remain separate. Missing publisher lifecycle inputs cannot establish latency or publication status. Domestic late completion is strictly after the Brasilia boundary on the target date; remaining open at that instant is a separate evidenced lifecycle interval. Overseas convention remains unavailable. Candidate attribution, BU reconciliation and model fitting are unavailable.",
        "challenge": "Inspect original-record lineage, exact line hashes, frozen expected indexes, source issue rows and reviewed evidence claims. Changed clock bounds, missing blocks, contradictory section assignments, unresolved copied histories or later authoritative lifecycle records can challenge classifications. Hashes attest stored-byte integrity, not the truth of a review assertion. Observed counts across shards can overlap; no confident global eligible total is asserted. Full lineage for legacy parses may be unavailable. No real-corpus pilot or real-message semantic adapter is certified by fixture acceptance.",
    },
    "pt-BR": {
        "title": "Relatório operacional inicial",
        "scope": "Corpus nacional parcial: logs disponíveis AC–RJ do segundo turno presidencial de 2026. Subconjuntos congelados preservam o denominador completo indexado; este relatório não estabelece completude nacional.",
        "labels": [
            "UFs congeladas declaradas (escopo do denominador completo por UF)",
            "Membros esperados no índice",
            "Membros preservados",
            "Objetos de conteúdo selecionados",
            "Objetos congelados analisados",
            "Sessões reconstruídas observadas",
            "Estados dos ciclos observados",
            "Total global de ciclos elegíveis",
            "Eventos normalizados de ciclo de vida",
            "Sobreposição entre fragmentos",
            "Linhagem de metadados",
            "Validação eleitoral",
            "Disponibilidade de votação tardia (sessões, sessões classificáveis)",
        ],
        "unknown": "indisponível / desconhecido",
        "inputs": "Entradas e cálculo",
        "assumptions": "Premissas e exclusões",
        "uncertainty": "Incerteza e evidências que podem contestar",
        "reproduce": "Reproduzir",
        "body": "Contagens usam eventos únicos de conteúdo e ciclos anônimos reconstruídos. Não são votos eleitorais reconciliados. Testemunhas de pacotes/membros/linhagem não multiplicam esses fatos. Seleção de sessões, relógios e históricos copiados exigem evidência revisada da origem. Recebimento, processamento, geração, publicação e observação do cliente permanecem separados. Ausência de dados de ciclo de vida do publicador não estabelece latência ou situação de publicação. Conclusão doméstica tardia ocorre estritamente após o limite de Brasília na data-alvo; permanecer aberta nesse instante é um intervalo de ciclo de vida comprovado separado. Convenção exterior continua indisponível. Atribuição a candidatos, reconciliação BU e ajuste de modelos estão indisponíveis.",
        "challenge": "Inspecione linhagem dos registros originais, hashes exatos de linhas, índices esperados congelados, registros de problemas e alegações de evidência revisada. Mudanças nos limites do relógio, blocos ausentes, atribuições contraditórias de seção, históricos copiados indefinidos ou registros posteriores autoritativos de ciclo de vida podem contestar classificações. Hashes atestam integridade dos bytes armazenados, não a veracidade de uma alegação de revisão. Contagens observadas entre fragmentos podem se sobrepor; nenhum total global elegível confiável é afirmado. Linhagem completa de parses antigos pode estar indisponível. Nenhum piloto do corpus real ou adaptador semântico de mensagens reais é certificado pela aceitação com fixtures.",
    },
}


def _mark_synthetic(path: Path, output: Path, document: JSON, products: list[Path]) -> list[Path]:
    """Pair report metadata and keep fixture reports visibly marked."""
    with open_release(path, _verified_document=document) as db:
        synthetic = db.execute(
            "SELECT count(*) FROM source_observation WHERE "
            "official_url LIKE 'fixture://%' OR official_url LIKE '%/synthetic-%'"
        ).fetchone()[0]
    identity = "EA-REPORT-" + path.name.upper()
    for product in products:
        if product.name.startswith("report.") and product.suffix == ".md":
            language = "pt-BR" if ".pt-BR." in product.name else "en"
            marker = ""
            if synthetic:
                marker = (
                    "SINTÉTICO — entradas de demonstração."
                    if ".pt-BR." in product.name
                    else "SYNTHETIC — demonstration inputs."
                )
                marker = "**" + marker + "**\n\n"
            product.write_text(
                f"Document-ID: {identity} · Revision: 1 · Language: {language}\n\n"
                + marker
                + product.read_text()
            )
    findings = output / "findings.json"
    value = json.loads(findings.read_text())
    value.update({"document_id": identity, "revision": 1})
    if synthetic:
        value["contains_synthetic_inputs"] = True
    findings.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    return products


def report_release(path: Path, output: str | Path, *, language: str = "both") -> list[Path]:
    """Write both translated Markdown reports by default, sharing one findings ledger."""
    if language not in ("en", "pt-BR", "both"):
        raise PublicationError("Report language must be en, pt-BR or both")
    path, output = resolve_release(path), Path(output).resolve()
    if output == path or output.is_relative_to(path):
        raise PublicationError("Report output must be outside immutable release")
    document = inspect_release(path)
    if document["identity"].get("producer") == "analysis-v1":
        from election_audit.analysis_reports import report_analysis

        return _mark_synthetic(
            path, output, document, report_analysis(path, output, document, language=language)
        )
    if document["identity"]["version"] == "derivative-release-v1":
        from election_audit.electoral_reports import report_electoral

        return _mark_synthetic(
            path, output, document, report_electoral(path, output, document, language=language)
        )
    validate_release(path, _verified_document=document)
    findings = _findings(path, output, document)
    output.mkdir(parents=True, exist_ok=True)
    values = [
        findings[key]
        for key in (
            "declared_ufs",
            "expected_members",
            "retained_members",
            "selected_objects",
            "expected_objects",
            "observed_sessions",
            "observed_cycle_states",
            "global_eligible_cycle_total",
            "normalized_lifecycle_events",
            "cross_shard_overlap",
            "metadata_lineage_state",
            "electoral_validation",
            "late_voting_availability",
        )
    ]
    products = {}
    for lang in ("en", "pt-BR") if language == "both" else (language,):
        words = TEXT[lang]
        lines = [f"# {words['title']}", "", words["scope"], "", f"`{findings['release_id']}`", ""]
        for label, value in zip(words["labels"], values, strict=True):
            lines.append(
                f"- {label}: {words['unknown'] if value is None else json.dumps(value, ensure_ascii=False)}"
            )
        lines += [
            "",
            f"## {words['inputs']}",
            "",
            "```json",
            json.dumps(findings["inputs"], indent=2),
            "```",
            "",
        ]
        for sql in (COUNT_SQL, LIFECYCLE_SQL, LATE_SQL):
            lines += ["```sql", sql, "```", ""]
        lines += [
            "```text",
            findings["calculations"]["late_boundary"],
            findings["calculations"]["late_share"],
            "```",
            "",
            f"## {words['assumptions']}",
            "",
            words["body"],
            "",
            f"## {words['uncertainty']}",
            "",
            words["challenge"],
            "",
            f"## {words['reproduce']}",
            "",
            "```sh",
            f"rtk proxy env UV_OFFLINE=1 just validate '{path}'",
            f"rtk proxy env UV_OFFLINE=1 just query '{path}' --sql '{COUNT_SQL}'",
            "```",
            "",
        ]
        products[f"report.{lang}.md"] = "\n".join(lines)
    products["lifecycle.sql"] = LIFECYCLE_SQL + ";\n"
    products["late.sql"] = LATE_SQL + ";\n"
    products["findings.json"] = (
        json.dumps(findings, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    for name, contents in products.items():
        # Atomic per-file replacement; immutable releases remain untouched.
        descriptor, temporary = tempfile.mkstemp(prefix=".report-", dir=output)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(output / name)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return _mark_synthetic(path, output, document, [output / name for name in products])


def release_main(command: str, argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    if command == "build":
        parser.add_argument("inputs", nargs="+", type=Path)
        parser.add_argument(
            "--input-kind",
            choices=("reconstruction", "parse", "snapshot"),
            default="reconstruction",
        )
        parser.add_argument("--store", required=True, type=Path)
        parser.add_argument("--evidence", type=Path)
        for key, default in ResourceConfig().__dict__.items():
            parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    else:
        parser.add_argument("release", type=Path)
        if command == "query":
            sql_options = parser.add_mutually_exclusive_group(required=True)
            sql_options.add_argument("--sql")
            sql_options.add_argument("--sql-file", type=Path)
            parser.add_argument("--max-rows", type=int, default=1000)
        if command == "report":
            parser.add_argument("--output", required=True, type=Path)
            parser.add_argument("--language", choices=("en", "pt-BR", "both"), default="both")
    args = parser.parse_args(argv)
    try:
        if command == "build":
            config = ResourceConfig(
                **{key: getattr(args, key) for key in ResourceConfig().__dict__}
            )
            evidence = json.loads(args.evidence.read_text()) if args.evidence else None
            if args.input_kind != "reconstruction" and len(args.inputs) != 1:
                raise PublicationError("Snapshot/parse builds require exactly one frozen input")
            if args.input_kind == "reconstruction" and evidence:
                raise PublicationError("Evidence belongs to parse/snapshot reconstruction builds")
            result = (
                publish_release(args.inputs, args.store, config=config)
                if args.input_kind == "reconstruction"
                else (build_from_parse if args.input_kind == "parse" else build_from_snapshot)(
                    args.inputs[0], args.store, config=config, evidence=evidence
                )
            )
        elif command == "validate":
            result = validate_release(args.release)
        elif command == "query":
            result = query_release(
                args.release,
                args.sql if args.sql is not None else args.sql_file.read_text(),
                max_rows=args.max_rows,
            )
        elif command == "report":
            result = report_release(args.release, args.output, language=args.language)
        else:
            raise PublicationError("Unknown release command")
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.error(str(exc))
    print(
        str(result)
        if isinstance(result, Path)
        else json.dumps(result, ensure_ascii=False, default=str)
    )
    return 0
