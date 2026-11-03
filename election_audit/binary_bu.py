"""Schema-driven BU decoding; schema origin and signature trust stay explicit."""

import hashlib
from functools import lru_cache
from importlib.resources import files

SCHEMA_SHA = "e53e28e9812bb7e19cc4bcc77b6ce48f25c413f62a60369a91c4f269e19b7ed6"


@lru_cache(maxsize=1)
def codec():
    import asn1tools

    raw = files("election_audit").joinpath("resources/bu-2026-mirrored.asn1").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA:
        raise ValueError("BU schema digest mismatch")
    return asn1tools.compile_string(raw.decode(), codec="ber")


def decode_bu(raw, election):
    if not raw or len(raw) > 4 * 1024**2:
        raise ValueError("BU byte bound")
    parser = codec()
    envelope, consumed = parser.decode_with_length("EntidadeEnvelopeGenerico", raw)
    if (
        consumed != len(raw)
        or envelope["fase"] != "oficial"
        or envelope["tipoEnvelope"] != "envelopeBoletimUrna"
        or "seguranca" in envelope
    ):
        raise ValueError("Unsupported BU envelope, phase, encryption or trailing bytes")
    target = ("idPleito", int(election.pleito_code))
    if envelope["cabecalho"]["idEleitoral"] != target:
        raise ValueError("BU pleito mismatch")
    bu, consumed = parser.decode_with_length("EntidadeBoletimUrna", envelope["conteudo"])
    if (
        consumed != len(envelope["conteudo"])
        or bu["fase"] != "oficial"
        or bu["cabecalho"]["idEleitoral"] != target
    ):
        raise ValueError("BU content phase/pleito/length mismatch")
    section = bu["identificacaoSecao"]
    key = (
        str(section["municipioZona"]["municipio"]).zfill(5),
        str(section["municipioZona"]["zona"]).zfill(4),
        str(section["secao"]).zfill(4),
    )
    elections = [
        e
        for e in bu["resultadosVotacaoPorEleicao"]
        if e["idEleicao"] == int(election.election_code)
    ]
    if len(elections) != 1:
        raise ValueError("BU presidential election missing or duplicated")
    contest = elections[0]
    results = [
        (v, c)
        for v in contest["resultadosVotacao"]
        for c in v["totaisVotosCargo"]
        if c["codigoCargo"] == ("cargoConstitucional", "presidente")
    ]
    if len(results) != 1:
        raise ValueError("BU presidential contest missing or duplicated")
    voting, cargo = results[0]
    choices = {}
    for row in cargo["votosVotaveis"]:
        kind = row["tipoVoto"]
        if kind == "nominal":
            choice = str(row["identificacaoVotavel"]["codigo"])
            if not choice.isdigit() or not 1 <= int(choice) <= 94:
                raise ValueError("Invalid nominal code")
        elif kind in {"branco", "nulo", "cargoSemCandidato"}:
            if "identificacaoVotavel" in row:
                raise ValueError("Unexpected identification for noncandidate")
            choice = {"branco": "95", "nulo": "96", "cargoSemCandidato": "special:no_candidate"}[
                kind
            ]
        else:
            raise ValueError("Unsupported presidential vote category")
        count = row["quantidadeVotos"]
        if type(count) is not int or count < 0 or choice in choices:
            raise ValueError("Negative/duplicate BU choice")
        choices[choice] = count
    attendance = voting["qtdComparecimento"]
    if sum(choices.values()) != attendance or attendance != bu["qtdEleitoresCompareceram"]:
        raise ValueError("BU vote/attendance accounting mismatch")
    eligible = contest["qtdEleitoresAptos"]
    if (
        eligible < attendance
        or eligible != contest["qtdEleitoresAptosSecao"] + contest["qtdEleitoresAptosTTE"]
    ):
        raise ValueError("BU electorate accounting mismatch")
    carga = bu["urna"]["correspondenciaResultado"]["carga"]
    return {
        "key": key,
        "local": str(section["local"]).zfill(4),
        "urn_serial": str(carga["numeroInternoUrna"]),
        "emitted_raw": bu["dataHoraEmissao"],
        "eligible_electors": eligible,
        "attending_voters": attendance,
        "choices": choices,
        "software_version": bu["urna"]["versaoVotacao"],
        "schema_sha256": SCHEMA_SHA,
        "schema_provenance": "reviewed_public_mirror_original_TSE_ZIP_unavailable_HTTP403",
        "signature_status": "not_verified",
    }
