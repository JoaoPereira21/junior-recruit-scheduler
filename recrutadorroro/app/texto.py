"""Utilitários de texto: normalização, busca de termos e mascaramento de dados pessoais.

A normalização remove acentos e põe em minúsculas preservando o comprimento do texto,
para que uma posição encontrada no texto normalizado aponte para o mesmo trecho do
texto original (usado para mostrar a evidência exatamente como está no currículo).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _norm_char(c: str) -> str:
    decomposto = unicodedata.normalize("NFKD", c)
    base = "".join(x for x in decomposto if not unicodedata.combining(x)).lower()
    if len(base) == 1:
        return base
    minusculo = c.lower()
    return minusculo if len(minusculo) == 1 else c


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, com o mesmo comprimento do texto de entrada."""
    return "".join(_norm_char(c) for c in texto)


def preparar(texto: str) -> str:
    """Padroniza o texto extraído de um arquivo antes de guardá-lo."""
    texto = unicodedata.normalize("NFC", texto).replace("﻿", "")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    linhas = [re.sub(r"[  ]+", " ", linha).strip() for linha in texto.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


# ---------------------------------------------------------------- termos

_SEP_LETRAS = r"[\s\-\./]?"
_SEP_PALAVRAS = r"[\s\-\./,]*"


def _padrao_variante(variante: str) -> str | None:
    tokens = re.findall(r"[a-z0-9+#]+", normalizar(variante))
    if not tokens:
        return None
    partes = [_SEP_LETRAS.join(re.escape(ch) for ch in tok) for tok in tokens]
    return r"(?<![a-z0-9])" + _SEP_PALAVRAS.join(partes) + r"(?![a-z0-9])"


def variantes(termo: str) -> list[str]:
    """'TOTVS RM | Protheus' -> ['TOTVS RM', 'Protheus']."""
    return [v.strip() for v in termo.split("|") if v.strip()]


def compilar(termo: str) -> re.Pattern[str] | None:
    """Expressão que encontra o termo (e seus sinônimos separados por '|') no texto
    normalizado, tolerando variações de escrita como 'eSocial', 'e-Social', 'E Social'
    ou 'DCTFWeb' / 'DCTF Web'."""
    padroes = [p for p in (_padrao_variante(v) for v in variantes(termo)) if p]
    if not padroes:
        return None
    return re.compile("|".join(f"(?:{p})" for p in padroes))


@dataclass
class Ocorrencia:
    inicio: int
    fim: int


def encontrar(termo: str, texto_normalizado: str) -> list[Ocorrencia]:
    padrao = compilar(termo)
    if padrao is None:
        return []
    return [Ocorrencia(m.start(), m.end()) for m in padrao.finditer(texto_normalizado)]


def linha_de(texto: str, posicao: int, limite: int = 220) -> str:
    """A linha do texto original que contém a posição (cortada se for muito longa)."""
    inicio = texto.rfind("\n", 0, posicao) + 1
    fim = texto.find("\n", posicao)
    fim = len(texto) if fim == -1 else fim
    linha = texto[inicio:fim].strip()
    if len(linha) <= limite:
        return linha
    rel = posicao - inicio
    a = max(0, rel - limite // 2)
    return ("…" if a > 0 else "") + linha[a : a + limite].strip() + "…"


# ---------------------------------------------------------------- LGPD

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_TELEFONE = re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\s?\d{4}[\s-]?\d{4}\b")
_LINK = re.compile(r"(?:https?://|www\.)\S+|linkedin\.com/\S+", re.IGNORECASE)


def mascarar(texto: str) -> str:
    """Esconde e-mail, CPF, telefone e links pessoais antes de exibir o texto."""
    texto = _EMAIL.sub("[e-mail oculto]", texto)
    texto = _CPF.sub("[CPF oculto]", texto)
    texto = _TELEFONE.sub("[telefone oculto]", texto)
    return _LINK.sub("[link oculto]", texto)
