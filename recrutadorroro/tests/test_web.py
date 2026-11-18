import io

import pytest
from fastapi.testclient import TestClient

from app.exemplo import PASTA_EXEMPLOS, VAGA_EXEMPLO


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("RECRUTADOR_DB", str(tmp_path / "teste.db"))
    monkeypatch.delenv("RECRUTADOR_USUARIO", raising=False)
    monkeypatch.delenv("RECRUTADOR_SENHA", raising=False)
    from app.main import app

    return TestClient(app)


def criar_vaga(cliente) -> int:
    dados = {k: str(v) for k, v in VAGA_EXEMPLO.items()}
    r = cliente.post("/vagas", data=dados, follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def enviar_exemplos(cliente, vaga_id):
    arquivos = [("arquivos", (f.name, f.read_bytes(), "text/plain")) for f in sorted(PASTA_EXEMPLOS.glob("*.txt"))]
    return cliente.post(f"/vagas/{vaga_id}/curriculos", files=arquivos)


def test_fluxo_completo(cliente):
    assert "Nenhuma vaga" in cliente.get("/").text
    vaga_id = criar_vaga(cliente)

    r = enviar_exemplos(cliente, vaga_id)
    assert r.status_code == 200
    assert "5 currículo(s) adicionado(s)" in r.text
    assert r.text.index("candidato_A.txt") < r.text.index("candidato_B.txt")

    # reenvio é ignorado
    assert "já estavam nesta vaga" in enviar_exemplos(cliente, vaga_id).text

    # detalhe e decisão
    pagina = cliente.get(f"/vagas/{vaga_id}/candidatos/1")
    assert pagina.status_code == 200 and "Avaliação por critério" in pagina.text
    r = cliente.post(f"/vagas/{vaga_id}/candidatos/1/decisao", data={"decisao": "entrevistar", "observacao": "ok"},
                     follow_redirects=False)
    assert r.status_code == 303

    csv = cliente.get(f"/vagas/{vaga_id}/exportar.csv")
    assert csv.status_code == 200 and "Entrevistar" in csv.text and csv.text.startswith("﻿")

    busca = cliente.get("/busca", params={"q": "eSocial, TOTVS RM | Senior"})
    assert "candidato_A.txt" in busca.text and "candidato_D.txt" not in busca.text

    # excluir a vaga apaga os currículos
    cliente.post(f"/vagas/{vaga_id}/excluir")
    assert cliente.get(f"/vagas/{vaga_id}").status_code == 404
    assert "candidato_A.txt" not in cliente.get("/busca", params={"q": "eSocial"}).text


def test_editar_criterios_reavalia(cliente):
    vaga_id = criar_vaga(cliente)
    enviar_exemplos(cliente, vaga_id)
    dados = {k: str(v) for k, v in VAGA_EXEMPLO.items()}
    dados["obrigatorias"] = "folha de pagamento"
    dados["formacao_minima"] = "0"
    cliente.post(f"/vagas/{vaga_id}/editar", data=dados)
    pagina = cliente.get(f"/vagas/{vaga_id}/candidatos/3")  # candidato C passa a atender
    assert "Atende" in pagina.text and "Não cita" not in pagina.text


def test_validacao_do_formulario(cliente):
    r = cliente.post("/vagas", data={"titulo": "", "obrigatorias": ""})
    assert r.status_code == 400 and "Informe o título" in r.text


def test_arquivo_invalido(cliente):
    vaga_id = criar_vaga(cliente)
    r = cliente.post(f"/vagas/{vaga_id}/curriculos", files=[("arquivos", ("foto.png", io.BytesIO(b"x"), "image/png"))])
    assert r.status_code == 400 and "formato não aceito" in r.text


def test_senha_opcional(cliente, monkeypatch):
    monkeypatch.setenv("RECRUTADOR_USUARIO", "rh")
    monkeypatch.setenv("RECRUTADOR_SENHA", "segredo")
    assert cliente.get("/").status_code == 401
    assert cliente.get("/", auth=("rh", "segredo")).status_code == 200
