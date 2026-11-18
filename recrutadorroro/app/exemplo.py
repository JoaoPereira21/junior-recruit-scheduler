"""Carrega uma vaga de exemplo com os currículos fictícios de `exemplos/curriculos`.

Uso (dentro da pasta recrutadorroro):  python -m app.exemplo
"""

from __future__ import annotations

from pathlib import Path

from . import db
from .extracao import extrair_texto

PASTA_EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos" / "curriculos"

VAGA_EXEMPLO = {
    "titulo": "Analista de Departamento Pessoal Pleno (exemplo)",
    "descricao": "Vaga fictícia para demonstração do RecrutadorRORO.",
    "obrigatorias": "\n".join([
        "folha de pagamento", "rescisão | rescisões", "férias", "admissão | admissões",
        "eSocial", "FGTS Digital", "DCTFWeb",
    ]),
    "minimo_obrigatorias": 100,
    "desejaveis": "\n".join(["TOTVS RM | Senior", "Excel avançado", "saúde | hospital | clínica", "PJ"]),
    "anos_minimos": 3.0,
    "termos_area": "departamento pessoal\nDP",
    "formacao_minima": 2,
    "cursos": "Administração\nRecursos Humanos\nCiências Contábeis",
    "cidades": "Fortaleza",
    "modalidade": "presencial",
}


def carregar() -> int:
    vaga_id = db.salvar_vaga(VAGA_EXEMPLO)
    for arquivo in sorted(PASTA_EXEMPLOS.glob("*.txt")):
        db.adicionar_candidato(vaga_id, arquivo.name, extrair_texto(arquivo.name, arquivo.read_bytes()))
    return vaga_id


if __name__ == "__main__":
    vaga_id = carregar()
    print(f"Vaga de exemplo criada (id {vaga_id}). Abra http://127.0.0.1:8000/vagas/{vaga_id}")
