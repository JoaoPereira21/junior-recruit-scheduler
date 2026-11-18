from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.avaliacao import ATENDE, NAO_ATENDE, Vaga, avaliar
from app.lecom import NaoEhLecom, importar_pdf, interpretar

PASTA = Path(__file__).resolve().parent.parent / "exemplos" / "lecom"
PDF = PASTA / "solicitacao_ficticia.pdf"


@pytest.fixture(scope="module")
def importacao():
    return importar_pdf(PDF.read_bytes())


def test_le_titulo_codigo_e_campos_em_colunas(importacao):
    d = importacao.dados
    assert d["titulo"] == "Analista SAP BASIS Sênior (Lecom 9.999.001)"
    assert d["modalidade"] == "remoto"
    resumo = dict(importacao.resumo)
    # campos lado a lado no PDF: cada valor fica com o seu rótulo
    assert resumo["Cargo"] == "ESPECIALISTA DE INFRA SAP"
    assert resumo["Área"] == "TI - DATACENTER"
    assert resumo["Senioridade"] == "Especialista"


def test_requisitos_viram_obrigatorias_e_diferenciais_desejaveis(importacao):
    obrig = importacao.dados["obrigatorias"].splitlines()
    desej = importacao.dados["desejaveis"].splitlines()
    assert obrig[0] == "BASIS"  # "experiência comprovada em BASIS"
    for termo in ["S/4HANA", "HANA Cockpit", "HSR", "PI/PO", "GRC", "SolMan", "STMS", "HA/DR", "Linux"]:
        assert termo in obrig
    assert "DNS" in desej  # "noções de" vira desejável
    assert "Nutanix" in desej and "SAProuter" in desej and "ITIL" in desej
    assert importacao.dados["termos_area"] == "BASIS"
    assert importacao.dados["minimo_obrigatorias"] == 70


def test_nao_guarda_dados_pessoais_do_formulario(importacao):
    tudo = " ".join(str(v) for v in importacao.dados.values())
    for dado in ["Pessoa Solicitante", "solicitante@exemplo.com", "90000-0000", "DIRETORIA FICTICIA",
                 "R$", "Justificativa", "Pessoa Validadora", "9.999.000"]:
        assert dado not in tudo


def test_documento_que_nao_e_lecom():
    with pytest.raises(NaoEhLecom):
        interpretar("Currículo qualquer\nExperiência", {})


def test_avaliacao_dos_curriculos_sap(importacao):
    d = importacao.dados
    vaga = Vaga(
        titulo=d["titulo"], obrigatorias=d["obrigatorias"].splitlines(), minimo_obrigatorias=d["minimo_obrigatorias"],
        desejaveis=d["desejaveis"].splitlines(), termos_area=d["termos_area"].splitlines(), modalidade=d["modalidade"],
    )
    hoje = date(2026, 11, 18)
    r = {f.stem: avaliar(vaga, f.read_text(encoding="utf-8"), hoje) for f in (PASTA / "curriculos").glob("*.txt")}
    assert r["sap_basis_1"].situacao == ATENDE
    assert r["sap_basis_2"].situacao == NAO_ATENDE and "abaixo do mínimo de 70%" in r["sap_basis_2"].motivos[0]
    assert r["infra_3"].situacao == NAO_ATENDE and r["infra_3"].anos_area == 0
    assert r["sap_basis_1"].nota > r["sap_basis_2"].nota > r["infra_3"].nota


def test_tela_de_importacao(tmp_path, monkeypatch):
    monkeypatch.setenv("RECRUTADOR_DB", str(tmp_path / "t.db"))
    from app.main import app

    cliente = TestClient(app)
    r = cliente.post("/vagas/importar-lecom", files={"arquivo": ("lecom.pdf", PDF.read_bytes(), "application/pdf")})
    assert r.status_code == 200
    assert "Importado do Lecom" in r.text and "HANA Cockpit" in r.text and 'value="70"' in r.text
    assert "solicitante@exemplo.com" not in r.text
    # importar só preenche o formulário: nada é salvo até o recrutador confirmar
    assert db.vagas() == []

    r = cliente.post("/vagas/importar-lecom", files={"arquivo": ("cv.txt", b"texto", "text/plain")})
    assert r.status_code == 400 and "precisa ser PDF" in r.text
