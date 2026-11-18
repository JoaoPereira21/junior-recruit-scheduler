"""Armazenamento local em SQLite.

Guarda só o texto extraído dos currículos, nunca o arquivo original. O banco fica em
`dados/` (fora do Git) e cada vaga pode ser excluída junto com todos os seus currículos.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .avaliacao import Vaga

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "dados"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    obrigatorias TEXT NOT NULL DEFAULT '',
    desejaveis TEXT NOT NULL DEFAULT '',
    anos_minimos REAL NOT NULL DEFAULT 0,
    termos_area TEXT NOT NULL DEFAULT '',
    formacao_minima INTEGER NOT NULL DEFAULT 0,
    cursos TEXT NOT NULL DEFAULT '',
    cidades TEXT NOT NULL DEFAULT '',
    modalidade TEXT NOT NULL DEFAULT 'presencial',
    criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    texto TEXT NOT NULL,
    hash TEXT NOT NULL,
    decisao TEXT NOT NULL DEFAULT 'pendente',
    observacao TEXT NOT NULL DEFAULT '',
    enviado_em TEXT NOT NULL,
    UNIQUE (vaga_id, hash)
);
"""

CAMPOS_LISTA = ("obrigatorias", "desejaveis", "termos_area", "cursos", "cidades")
DECISOES = ("pendente", "entrevistar", "reprovado")


def caminho_banco() -> Path:
    return Path(os.environ.get("RECRUTADOR_DB", PASTA_PADRAO / "recrutador.db"))


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    caminho = caminho_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(_ESQUEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def lista(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def para_vaga(linha: sqlite3.Row) -> Vaga:
    return Vaga(
        titulo=linha["titulo"],
        obrigatorias=lista(linha["obrigatorias"]),
        desejaveis=lista(linha["desejaveis"]),
        anos_minimos=linha["anos_minimos"],
        termos_area=lista(linha["termos_area"]),
        formacao_minima=linha["formacao_minima"],
        cursos=lista(linha["cursos"]),
        cidades=lista(linha["cidades"]),
        modalidade=linha["modalidade"],
    )


# ---------------------------------------------------------------- vagas

def salvar_vaga(dados: dict, vaga_id: int | None = None) -> int:
    campos = ("titulo", "descricao", "obrigatorias", "desejaveis", "anos_minimos", "termos_area",
              "formacao_minima", "cursos", "cidades", "modalidade")
    valores = [dados[c] for c in campos]
    with conectar() as con:
        if vaga_id is None:
            cur = con.execute(
                f"INSERT INTO vagas ({', '.join(campos)}, criada_em) VALUES ({', '.join('?' * len(campos))}, ?)",
                [*valores, _agora()],
            )
            return int(cur.lastrowid)
        con.execute(f"UPDATE vagas SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?", [*valores, vaga_id])
        return vaga_id


def vagas() -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute(
            """SELECT v.*, COUNT(c.id) AS total,
                      SUM(c.decisao = 'entrevistar') AS entrevistar
               FROM vagas v LEFT JOIN candidatos c ON c.vaga_id = v.id
               GROUP BY v.id ORDER BY v.id DESC"""
        ).fetchall()


def vaga(vaga_id: int) -> sqlite3.Row | None:
    with conectar() as con:
        return con.execute("SELECT * FROM vagas WHERE id = ?", (vaga_id,)).fetchone()


def excluir_vaga(vaga_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM vagas WHERE id = ?", (vaga_id,))


# ---------------------------------------------------------------- candidatos

def adicionar_candidato(vaga_id: int, arquivo: str, texto: str) -> bool:
    """Devolve False se o mesmo currículo já tinha sido enviado para esta vaga."""
    resumo = hashlib.sha256(texto.encode()).hexdigest()
    with conectar() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO candidatos (vaga_id, arquivo, texto, hash, enviado_em) VALUES (?, ?, ?, ?, ?)",
            (vaga_id, arquivo, texto, resumo, _agora()),
        )
        return cur.rowcount == 1


def candidatos(vaga_id: int) -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute("SELECT * FROM candidatos WHERE vaga_id = ? ORDER BY id", (vaga_id,)).fetchall()


def todos_candidatos() -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute(
            "SELECT c.*, v.titulo AS vaga_titulo FROM candidatos c JOIN vagas v ON v.id = c.vaga_id ORDER BY c.id DESC"
        ).fetchall()


def candidato(vaga_id: int, candidato_id: int) -> sqlite3.Row | None:
    with conectar() as con:
        return con.execute(
            "SELECT * FROM candidatos WHERE id = ? AND vaga_id = ?", (candidato_id, vaga_id)
        ).fetchone()


def decidir(vaga_id: int, candidato_id: int, decisao: str, observacao: str) -> None:
    if decisao not in DECISOES:
        raise ValueError(decisao)
    with conectar() as con:
        con.execute(
            "UPDATE candidatos SET decisao = ?, observacao = ? WHERE id = ? AND vaga_id = ?",
            (decisao, observacao.strip(), candidato_id, vaga_id),
        )


def excluir_candidato(vaga_id: int, candidato_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM candidatos WHERE id = ? AND vaga_id = ?", (candidato_id, vaga_id))
