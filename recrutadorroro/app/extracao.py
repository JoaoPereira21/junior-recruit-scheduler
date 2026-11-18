"""Leitura do texto de currículos em PDF, Word (.docx) ou texto (.txt / .md)."""

from __future__ import annotations

import io
from pathlib import Path

from .texto import preparar

EXTENSOES = {".pdf", ".docx", ".txt", ".md"}


class ArquivoInvalido(ValueError):
    pass


def _pdf(conteudo: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)


def _docx(conteudo: bytes) -> str:
    import docx

    documento = docx.Document(io.BytesIO(conteudo))
    partes = [p.text for p in documento.paragraphs]
    for tabela in documento.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(celula.text for celula in linha.cells))
    return "\n".join(partes)


def _txt(conteudo: bytes) -> str:
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("utf-8", errors="replace")


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    extensao = Path(nome_arquivo).suffix.lower()
    if extensao not in EXTENSOES:
        raise ArquivoInvalido(f"{nome_arquivo}: formato não aceito (use PDF, DOCX ou TXT)")
    try:
        if extensao == ".pdf":
            bruto = _pdf(conteudo)
        elif extensao == ".docx":
            bruto = _docx(conteudo)
        else:
            bruto = _txt(conteudo)
    except Exception as erro:  # arquivo corrompido ou protegido por senha
        raise ArquivoInvalido(f"{nome_arquivo}: não foi possível ler o arquivo ({erro.__class__.__name__})") from erro
    return preparar(bruto)
