"""Bilingual electoral findings over one verified, immutable parent chain."""

import json
import os
import tempfile
from pathlib import Path

from election_audit.derivatives import release_layers
from election_audit.publication import PublicationError, open_release
from election_audit.types import JSON

SQL = {
    "selection": "SELECT selection_state, count(*) AS results FROM canonical_result GROUP BY selection_state ORDER BY selection_state",
    "reconciliation": "SELECT json_extract_string(payload, '$.state') AS state, count(*) AS results FROM result_reconciliation GROUP BY state ORDER BY state",
    "unanimity": "SELECT count(*) FILTER (WHERE json_extract_string(payload, '$.availability')='available') AS eligible_results, count(*) FILTER (WHERE json_extract(payload, '$.strict_unanimity')::BOOLEAN) AS strict_unanimous, count(*) FILTER (WHERE json_extract(payload, '$.all_valid_only_unanimity')::BOOLEAN) AS all_valid_only, count(*) FILTER (WHERE json_extract_string(payload, '$.availability')<>'available') AS unavailable FROM unanimous_results",
    "hierarchy": "SELECT json_extract_string(payload, '$.state') AS state, count(*) AS references FROM hierarchy_reconciliation GROUP BY state ORDER BY state",
    "timing": "SELECT interval_type, count(*) FILTER (WHERE json_extract_string(payload, '$.availability')='known_pair') AS known_pairs, count(*) FILTER (WHERE json_extract(payload, '$.negative')::BOOLEAN) AS negative_pairs, count(*) FILTER (WHERE json_extract(payload, '$.repeated_or_corrected')::BOOLEAN) AS repeated_pairs, count(*) FILTER (WHERE json_extract_string(payload, '$.availability')<>'known_pair') AS unavailable FROM result_timing GROUP BY interval_type ORDER BY interval_type",
    "rounds": "SELECT json_extract_string(payload, '$.availability') AS availability, count(*) AS populations FROM round_comparison GROUP BY availability ORDER BY availability",
}
TEXT: dict[str, JSON] = {
    "en": {
        "title": "Electoral reconciliation report",
        "scope": "Partial national population. Available operational inputs cover AC–RJ 2026 presidential runoff logs; explicitly imported results do not establish national completeness.",
        "validation": "Real BU validation unavailable. This release checks a normalized contract and its arithmetic. No verified official TSE 2026 BU adapter, real BU validation or signature certification is supplied by these fixtures.",
        "labels": [
            "Canonical selection",
            "Version reconciliation",
            "Unanimity",
            "Final hierarchy",
            "Result timing",
            "Round comparison",
        ],
        "body": "Each principal/contest/snapshot contributes at most one eligible totalized result. Conflicting versions are unavailable; received/rejected/excluded versions do not contribute votes. Electorate and attendance occur once per result, independently of long choice rows. Unknown categories and missing choices remain unknown. Strict unanimity requires positive total ballots, exactly one candidate receiving every ballot and zero blank/null/special/unresolved votes with complete, reconciled choices. All-valid-only unanimity has a separate denominator. Zero ballots are unavailable for strict unanimity. Physical urn contributions and candidate attribution to log cycles are unavailable.",
        "timing": "Timing denominators are known endpoint pairs for the named interval. Missing clocks, negative intervals and repeated/corrected event pairs are retained separately. Client observations never replace publisher receipt/publication. Round comparison uses only explicitly reviewed disjoint whole-principal populations and aggregates each round before joining; candidate identities and individual vote transfers are not inferred.",
        "evidence": "Provenance and reproduction",
        "challenge": "Inspect original imported bytes, exact source locators, status/supersession anchors, expected choices, composition, electorate, hierarchy coverage including ZZ, clock rules and harmonization evidence. Later official corrections, missing overseas units or contradictory source meanings can challenge these results. The findings bundle pins the complete parent chain; relocate the whole relative chain together. Byte hashes certify stored integrity only.",
    },
    "pt-BR": {
        "title": "Relatório de reconciliação eleitoral",
        "scope": "População nacional parcial. Entradas operacionais disponíveis cobrem logs AC–RJ do segundo turno presidencial de 2026; resultados importados explicitamente não estabelecem completude nacional.",
        "validation": "Validação de BU real indisponível. Esta publicação verifica um contrato normalizado e sua aritmética. As fixtures não fornecem adaptador BU oficial TSE 2026 verificado, validação de BU real ou certificação de assinatura.",
        "labels": [
            "Seleção canônica",
            "Reconciliação de versões",
            "Unanimidade",
            "Hierarquia final",
            "Tempos dos resultados",
            "Comparação de turnos",
        ],
        "body": "Cada principal/disputa/snapshot contribui com no máximo um resultado elegível totalizado. Versões conflitantes ficam indisponíveis; versões recebidas/rejeitadas/excluídas não contribuem votos. Eleitorado e comparecimento ocorrem uma vez por resultado, separados das escolhas em formato longo. Categorias desconhecidas e escolhas ausentes permanecem desconhecidas. Unanimidade estrita exige total positivo de cédulas, exatamente um candidato com todas as cédulas e zero votos brancos/nulos/especiais/não resolvidos, com escolhas completas e reconciliadas. Unanimidade apenas entre válidos tem denominador separado. Zero cédulas fica indisponível para unanimidade estrita. Contribuições de urnas físicas e atribuição de candidatos a ciclos dos logs estão indisponíveis.",
        "timing": "Denominadores temporais são pares de extremos conhecidos do intervalo nomeado. Relógios ausentes, intervalos negativos e pares de eventos repetidos/corrigidos são preservados separadamente. Observações do cliente nunca substituem recebimento/publicação do publicador. Comparação de turnos usa apenas populações disjuntas de principais inteiros revisadas explicitamente e agrega cada turno antes da junção; identidades de candidatos e transferências individuais de votos não são inferidas.",
        "evidence": "Proveniência e reprodução",
        "challenge": "Inspecione bytes originais importados, localizadores exatos, âncoras de situação/supersessão, escolhas esperadas, composição, eleitorado, cobertura hierárquica incluindo ZZ, regras de relógio e evidência de harmonização. Correções oficiais posteriores, unidades ausentes no exterior ou significados contraditórios da origem podem contestar resultados. O pacote de achados fixa a cadeia completa de pais; mova toda a cadeia relativa junta. Hashes dos bytes certificam apenas integridade armazenada.",
    },
}


def report_electoral(
    path: Path, output: str | Path, document: JSON, *, language: str = "both"
) -> list[Path]:
    from election_audit.release_tools import _query_connection, _restrict_query, validate_release

    output = Path(output).resolve()
    for root, _ in release_layers(path, document):
        if output == root or output.is_relative_to(root):
            raise PublicationError(
                "Report output must be outside every immutable parent/child release"
            )
    validation = validate_release(path, _verified_document=document)
    with open_release(path, _verified_document=document) as connection:
        _restrict_query(connection, path, document)
        calculations = {key: _query_connection(connection, sql, 1000) for key, sql in SQL.items()}
    chain = [
        {
            "release_id": root.name,
            "identity": doc["identity"],
            "files": doc["files"],
            "tables": doc.get("combined_tables", doc["tables"]),
        }
        for root, doc in release_layers(path, document)
    ]
    findings: JSON = {
        "release_id": path.name,
        "national_status": "partial_national",
        "electoral_validation": document["electoral_validation"],
        "verification_status": document.get("verification_status", "normalized_only"),
        "validation": validation,
        "calculations": calculations,
        "sql": SQL,
        "parent_chain": chain,
        "assumptions": "reviewed_normalized_status_completeness_clocks_and_harmonization_assertions",
        "exclusions": "unresolved_versions_missing_categories_non_totalized_results_unmatched_populations",
        "uncertainty": "final_status_completeness_independent_hierarchy_clocks_and_signatures_require_separate_evidence",
        "challenging_evidence": "original_bytes_official_corrections_composition_ZZ_coverage_category_dictionary_clocks",
        "reproduce": f"rtk proxy env UV_OFFLINE=1 just report '{path}' --output '{output}'",
    }
    products = {
        "findings.json": json.dumps(findings, ensure_ascii=False, indent=2, default=str) + "\n"
    }
    for lang in ("en", "pt-BR") if language == "both" else (language,):
        text = TEXT[lang]
        lines = [
            "# " + text["title"],
            "",
            text["scope"],
            "",
            (
                "Official BWEB layout verified; published-row arithmetic checked. Final totalization, "
                "complete choices, independent final totals and signatures remain unverified."
                if lang == "en"
                else "Leiaute BWEB oficial verificado; aritmética das linhas publicadas conferida. Totalização final, "
                "escolhas completas, totais finais independentes e assinaturas permanecem não verificados."
            )
            if document.get("verification_status") == "official_layout_verified"
            else text["validation"],
            "",
            text["body"],
            "",
            text["timing"],
            "",
        ]
        for label, (key, calculation) in zip(text["labels"], calculations.items(), strict=True):
            lines += [
                f"**{label}**",
                "",
                "```json",
                json.dumps(calculation, ensure_ascii=False, default=str),
                "```",
                "",
                "```sql",
                SQL[key] + ";",
                "```",
                "",
            ]
        lines += [
            "## " + text["evidence"],
            "",
            text["challenge"],
            "",
            "```sh",
            findings["reproduce"],
            "```",
            "",
        ]
        products[f"report.{lang}.md"] = "\n".join(lines)
    products.update({key + ".sql": sql + ";\n" for key, sql in SQL.items()})
    output.mkdir(parents=True, exist_ok=True)
    for name, contents in products.items():
        fd, temporary = tempfile.mkstemp(prefix=".report-", dir=output)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(output / name)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return [output / name for name in products]
