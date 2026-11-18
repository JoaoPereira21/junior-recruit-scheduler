"""Busca de perfis em todos os currículos já recebidos, de qualquer vaga.

A consulta é uma lista de termos separados por vírgula; cada termo aceita sinônimos
com '|'. Ex.: "eSocial, TOTVS RM | Senior, Fortaleza". Os currículos aparecem do que
cita mais termos para o que cita menos, com o trecho onde cada termo foi encontrado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .texto import encontrar, linha_de, mascarar, normalizar, variantes


@dataclass
class Achado:
    termo: str
    trecho: str


@dataclass
class Perfil:
    candidato_id: int
    vaga_id: int
    vaga_titulo: str
    arquivo: str
    decisao: str
    encontrados: list[Achado] = field(default_factory=list)
    faltando: list[str] = field(default_factory=list)
    ocorrencias: int = 0


def termos_da_consulta(consulta: str) -> list[str]:
    return [t.strip() for t in consulta.split(",") if t.strip()]


def buscar(consulta: str, candidatos) -> tuple[list[str], list[Perfil]]:
    termos = termos_da_consulta(consulta)
    if not termos:
        return [], []
    perfis = []
    for c in candidatos:
        normal = normalizar(c["texto"])
        perfil = Perfil(c["id"], c["vaga_id"], c["vaga_titulo"], c["arquivo"], c["decisao"])
        for termo in termos:
            rotulo = " / ".join(variantes(termo))
            ocorrencias = encontrar(termo, normal)
            if ocorrencias:
                perfil.encontrados.append(Achado(rotulo, mascarar(linha_de(c["texto"], ocorrencias[0].inicio))))
                perfil.ocorrencias += len(ocorrencias)
            else:
                perfil.faltando.append(rotulo)
        if perfil.encontrados:
            perfis.append(perfil)
    perfis.sort(key=lambda p: (-len(p.encontrados), -p.ocorrencias))
    return termos, perfis
