"""One shared calculation ledger with translated analysis report labels."""

import json
import os
import tempfile
from pathlib import Path

from election_audit.derivatives import release_layers
from election_audit.publication import PublicationError, open_release

SQL = {
    "features": "SELECT feature_id,readiness_state,count(*) AS components,count(value) AS numeric_values FROM audit_features GROUP BY feature_id,readiness_state ORDER BY feature_id,readiness_state",
    "partitions": "SELECT partition_name,count(*) AS observations,count(DISTINCT stable_location_id) AS locations FROM location_partition GROUP BY partition_name ORDER BY partition_name",
    "ledgers": "SELECT record_kind,count(*) AS records FROM analysis_ledger GROUP BY record_kind ORDER BY record_kind",
    "test_access": "SELECT access_state,count(*) AS locations FROM test_partition_status GROUP BY access_state ORDER BY access_state",
    "impact": "SELECT record_id,json_extract_string(payload,'$.availability') AS availability,json_extract(payload,'$.corrected_margin_bounds') AS conditional_margin_bounds FROM impact_scenario ORDER BY record_id",
}
TEXT = {
    "en": {
        "title": "Analysis foundation report",
        "features": "Feature availability",
        "partitions": "Location partitions",
        "ledgers": "Analysis and investigation ledgers",
        "test_access": "Test partition access",
        "impact": "Conditional impact scenarios",
        "scope": "Partial national AC–RJ scope. Normalized synthetic acceptance does not verify official BU compatibility or real electoral data. Numeric availability is separate from scientific eligibility.",
        "limits": "No fitted model, automatic fraud labels, certified p-values, FDR guarantee or final national margin. Unknown ratios remain unavailable. Device and logistics adjust specification 1 and can be mechanisms in specification 2; turnout, manual authorization and outages are not automatic controls. Missing temporal source evidence prevents predictive eligibility. Partition links are reviewed assertions, never inferred from school names or section codes. Inspecting a test partition makes it development data for future analyses. Conditional impact requires a specified mechanism, deduplicated population, caps and an explicitly assumed coherent margin; anonymous ballots are never attributed to candidates.",
        "evidence": "Reproduction and challenging evidence",
        "challenge": "The shared findings ledger contains exact SQL, source configuration and the pinned parent chain. Inspect original source bytes, schema mappings, composition and stable location link evidence, protocol families, every explored/null outcome, test access and alternative explanations. Hashes certify stored integrity only.",
    },
    "pt-BR": {
        "title": "Relatório da fundação analítica",
        "features": "Disponibilidade de variáveis",
        "partitions": "Partições por local de votação",
        "ledgers": "Registros de análise e investigação",
        "test_access": "Acesso à partição de teste",
        "impact": "Cenários de impacto condicional",
        "scope": "Escopo nacional parcial AC–RJ. Aceitação sintética normalizada não verifica compatibilidade com BU oficial nem dados eleitorais reais. Disponibilidade numérica é separada da elegibilidade científica.",
        "limits": "Sem modelo ajustado, rótulos automáticos de fraude, valores-p certificados, garantia de FDR ou margem nacional final. Razões desconhecidas permanecem indisponíveis. Equipamento e logística ajustam a especificação 1 e podem ser mecanismos na especificação 2; comparecimento, autorização manual e interrupções não são controles automáticos. Ausência de evidência temporal da origem impede elegibilidade preditiva. Vínculos de locais são alegações revisadas, nunca inferidos de nomes de escolas ou códigos de seção. Inspecionar a partição de teste a transforma em dados de desenvolvimento para análises futuras. Impacto condicional exige mecanismo especificado, população deduplicada, limites e margem coerente assumida explicitamente; cédulas anônimas nunca são atribuídas a candidatos.",
        "evidence": "Reprodução e evidências que podem contestar",
        "challenge": "O registro compartilhado de achados contém SQL exato, configuração da origem e cadeia de pais fixada. Inspecione bytes originais, mapeamentos do esquema, composição e evidência dos vínculos estáveis de locais, famílias do protocolo, todos os resultados explorados/nulos, acesso ao teste e explicações alternativas. Hashes certificam apenas integridade armazenada.",
    },
}


def report_analysis(path, output, document, *, language="both"):
    from election_audit.archive_parsing import _read_checked
    from election_audit.release_tools import _query_connection, _restrict_query, validate_release

    output = Path(output).resolve()
    for root, _ in release_layers(path, document):
        if output == root or output.is_relative_to(root):
            raise PublicationError(
                "Report output must be outside every immutable parent/child release"
            )
    validation = validate_release(path, _verified_document=document)
    available = document["combined_tables"]
    sql = {
        key: value
        for key, value in SQL.items()
        if {
            "features": "audit_features",
            "partitions": "location_partition",
            "ledgers": "analysis_ledger",
            "test_access": "test_partition_status",
            "impact": "impact_scenario",
        }[key]
        in available
    }
    with open_release(path, _verified_document=document) as db:
        _restrict_query(db, path, document)
        calculations = {key: _query_connection(db, value, 1000) for key, value in sql.items()}
    findings = {
        "release_id": path.name,
        "national_status": "partial_national",
        "electoral_validation": document["electoral_validation"],
        "validation": validation,
        "sql": sql,
        "calculations": calculations,
        "configuration": _read_checked(path, "import.json")["analysis"],
        "parent_chain": [
            {
                "release_id": root.name,
                "identity": doc["identity"],
                "files": doc["files"],
                "tables": doc.get("combined_tables", doc["tables"]),
            }
            for root, doc in release_layers(path, document)
        ],
        "reproduce": f"rtk proxy env UV_OFFLINE=1 just report '{path}' --output '{output}'",
    }
    products = {
        "findings.json": json.dumps(findings, ensure_ascii=False, indent=2, default=str) + "\n"
    }
    for lang in ("en", "pt-BR") if language == "both" else (language,):
        words = TEXT[lang]
        lines = ["# " + words["title"], "", words["scope"], "", words["limits"], ""]
        for key, value in calculations.items():
            lines += [
                "**" + words[key] + "**",
                "",
                "```json",
                json.dumps(value, ensure_ascii=False, default=str),
                "```",
                "",
                "```sql",
                sql[key] + ";",
                "```",
                "",
            ]
        lines += [
            "## " + words["evidence"],
            "",
            words["challenge"],
            "",
            "```sh",
            findings["reproduce"],
            "```",
            "",
        ]
        products[f"report.{lang}.md"] = "\n".join(lines)
    products.update({key + ".sql": value + ";\n" for key, value in sql.items()})
    output.mkdir(parents=True, exist_ok=True)
    for name, content in products.items():
        fd, temporary = tempfile.mkstemp(prefix=".report-", dir=output)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(output / name)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return [output / name for name in products]
