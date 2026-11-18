from datetime import date
from pathlib import Path

import pytest

from app import analise
from app.avaliacao import ATENDE, NAO_ATENDE, VERIFICAR, Vaga, avaliar, chave_ranking
from app.exemplo import PASTA_EXEMPLOS, VAGA_EXEMPLO
from app.texto import encontrar, mascarar, normalizar

HOJE = date(2026, 11, 18)


def vaga_exemplo() -> Vaga:
    d = VAGA_EXEMPLO
    return Vaga(
        titulo=d["titulo"], obrigatorias=d["obrigatorias"].splitlines(), desejaveis=d["desejaveis"].splitlines(),
        anos_minimos=d["anos_minimos"], termos_area=d["termos_area"].splitlines(),
        formacao_minima=d["formacao_minima"], cursos=d["cursos"].splitlines(),
        cidades=d["cidades"].splitlines(), modalidade=d["modalidade"],
    )


@pytest.fixture(scope="module")
def resultados():
    vaga = vaga_exemplo()
    return {f.stem: avaliar(vaga, f.read_text(encoding="utf-8"), HOJE) for f in PASTA_EXEMPLOS.glob("*.txt")}


# ---------------------------------------------------------------- texto

def test_normalizar_preserva_tamanho():
    s = "Rescisões, Férias e Admissão — São Paulo"
    assert len(normalizar(s)) == len(s)
    assert normalizar(s).startswith("rescisoes, ferias")


@pytest.mark.parametrize("escrita", ["eSocial", "e-Social", "E Social", "ESOCIAL"])
def test_termo_tolera_variacoes(escrita):
    assert encontrar("eSocial", normalizar(f"Envio de eventos do {escrita} mensalmente"))


def test_termo_nao_casa_dentro_de_outra_palavra():
    assert not encontrar("PJ", normalizar("Projeto de melhoria"))
    assert encontrar("DCTFWeb", normalizar("Entrega da DCTF Web"))


def test_sinonimos():
    assert encontrar("TOTVS RM | Senior", normalizar("Sistema Senior de folha"))


def test_mascarar_dados_pessoais():
    s = mascarar("Contato: maria@exemplo.com, (85) 99999-1234, CPF 123.456.789-00")
    assert "maria@" not in s and "99999" not in s and "123.456" not in s


# ---------------------------------------------------------------- análise

def test_periodos_e_soma_sem_dupla_contagem():
    periodos = analise.achar_periodos(normalizar("jan/2018 a 12/2020 e 2020 - atual"), HOJE)
    assert [p.rotulo() for p in periodos] == ["2018–2020", "2020–atual"]
    assert analise.somar_meses(periodos) == (2026 - 2018) * 12 + 10


def test_formacao_niveis():
    texto = "Formação:\nBacharelado em Administração (concluído)\nMBA em Gestão de Pessoas (cursando)"
    niveis = [f.nivel for f in analise.extrair_formacoes(analise.separar_secoes(texto))]
    assert niveis == [3, 2]


def test_cidade_declarada():
    assert analise.cidade_declarada("Maria\nCaucaia - CE\nResumo") == "Caucaia - CE"


# ---------------------------------------------------------------- avaliação dos exemplos

def test_candidato_ideal_fica_em_primeiro(resultados):
    ordem = sorted(resultados, key=lambda k: chave_ranking(resultados[k]))
    assert ordem[0] == "candidato_A"
    assert ordem[-2:] == ["candidato_D", "candidato_B"]
    assert resultados["candidato_A"].situacao in (ATENDE, VERIFICAR)


def test_formacao_tecnica_nao_atende_superior(resultados):
    r = resultados["candidato_E"]
    assert r.situacao == NAO_ATENDE
    assert any("Formação" in m for m in r.motivos)
    assert any("Caucaia" in a for a in r.alertas)  # local só alerta, não elimina


def test_obrigatoria_faltando_elimina(resultados):
    r = resultados["candidato_C"]
    assert r.situacao == NAO_ATENDE
    assert "FGTS Digital" in r.motivos[0] and "DCTFWeb" in r.motivos[0]


def test_experiencia_fora_da_area_nao_conta(resultados):
    r = resultados["candidato_D"]
    assert r.anos_total > 5 and r.anos_area == 0


def test_evidencia_vem_do_curriculo(resultados):
    criterio = resultados["candidato_A"].criterio("Competências obrigatórias")
    esocial = next(i for i in criterio.itens if i.nome == "eSocial")
    assert "eSocial" in esocial.evidencia


def test_sem_criterios_de_formacao_e_remoto_nao_alerta_local():
    vaga = Vaga("Teste", obrigatorias=["Excel"], modalidade="remoto", cidades=["Fortaleza"])
    texto = (Path(PASTA_EXEMPLOS) / "candidato_B.txt").read_text(encoding="utf-8")
    r = avaliar(vaga, texto, HOJE)
    assert not any("Verifique disponibilidade" in a for a in r.alertas)
