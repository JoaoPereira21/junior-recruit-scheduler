"""Leitura estruturada de um currículo por regras: seções, experiência, formação e cidade.

Tudo aqui é heurístico. Por isso cada informação extraída guarda o trecho do currículo
de onde veio, para que o recrutador confira antes de decidir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .texto import compilar, normalizar

# ---------------------------------------------------------------- seções

_TITULOS = {
    "experiencia": [
        "experiencia profissional", "experiencias profissionais", "experiencias", "experiencia",
        "historico profissional", "trajetoria profissional", "atuacao profissional",
    ],
    "formacao": [
        "formacao academica", "formacao", "escolaridade", "educacao", "graduacao",
    ],
    "competencias": [
        "competencias", "habilidades", "conhecimentos", "ferramentas", "qualificacoes",
    ],
    "cursos": ["cursos complementares", "cursos", "certificacoes", "certificados", "idiomas"],
    "resumo": ["resumo profissional", "resumo", "objetivo", "perfil profissional", "perfil", "sobre mim"],
}


@dataclass
class Linha:
    texto: str
    normal: str
    inicio: int  # posição no texto completo


@dataclass
class Secoes:
    por_nome: dict[str, list[Linha]] = field(default_factory=dict)
    todas: list[Linha] = field(default_factory=list)

    def linhas(self, nome: str) -> list[Linha]:
        return self.por_nome.get(nome, [])


def _titulo(normal: str) -> tuple[str, str] | None:
    """Se a linha for um título de seção, devolve (seção, conteúdo após ':')."""
    limpo = normal.strip(" -•*:#").strip()
    for secao, nomes in _TITULOS.items():
        for nome in nomes:
            if limpo == nome:
                return secao, ""
            if limpo.startswith(nome) and re.match(r"\s*:", limpo[len(nome):]):
                resto = limpo[len(nome):].split(":", 1)[1].strip()
                return secao, resto
    return None


def separar_secoes(texto: str) -> Secoes:
    secoes = Secoes()
    atual = "cabecalho"
    pos = 0
    for bruta in texto.split("\n"):
        inicio = pos
        pos += len(bruta) + 1
        if not bruta.strip():
            continue
        normal = normalizar(bruta)
        achado = _titulo(normal) if len(bruta) <= 120 else None
        if achado:
            atual, resto = achado
            if not resto:
                continue
            desloc = len(bruta) - len(bruta.split(":", 1)[1].lstrip())
            linha = Linha(bruta[desloc:], normal[desloc:], inicio + desloc)
        else:
            linha = Linha(bruta, normal, inicio)
        secoes.por_nome.setdefault(atual, []).append(linha)
        secoes.todas.append(linha)
    return secoes


# ---------------------------------------------------------------- períodos

_MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
_DATA = (
    r"(?:(?P<{p}mn>\d{{1,2}})\s*/\s*|(?P<{p}mt>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
    r"[a-z]*\.?\s*(?:/|de)?\s*)?(?P<{p}a>(?:19|20)\d{{2}})"
)
_ATUAL = r"(?P<atual>atualmente|atual|presente|o momento|momento|hoje|o presente)"
_PERIODO = re.compile(
    _DATA.format(p="i") + r"\s*(?:-|–|—|a|ate|ao?)\s*(?:" + _DATA.format(p="f") + "|" + _ATUAL + ")"
)
_ANOS_DECLARADOS = re.compile(r"(\d{1,2})\+?\s*(?:anos?)\s+(?:de\s+)?(?:experiencia|atuacao|vivencia)")


@dataclass
class Periodo:
    inicio: tuple[int, int]  # (ano, mês)
    fim: tuple[int, int]
    atual: bool

    @property
    def meses(self) -> int:
        return max(1, (self.fim[0] - self.inicio[0]) * 12 + self.fim[1] - self.inicio[1])

    def rotulo(self) -> str:
        fim = "atual" if self.atual else str(self.fim[0])
        return f"{self.inicio[0]}–{fim}"


def _mes(m: re.Match[str], p: str) -> int | None:
    if m.group(f"{p}mn"):
        valor = int(m.group(f"{p}mn"))
        return valor if 1 <= valor <= 12 else None
    if m.group(f"{p}mt"):
        return _MESES[m.group(f"{p}mt")]
    return None


def achar_periodos(normal: str, hoje: date) -> list[Periodo]:
    periodos = []
    for m in _PERIODO.finditer(normal):
        ano_i = int(m.group("ia"))
        ini = (ano_i, _mes(m, "i") or 1)
        if m.group("atual"):
            fim, atual = (hoje.year, hoje.month), True
        else:
            fim, atual = (int(m.group("fa")), _mes(m, "f") or 1), False
        if fim < ini or ano_i > hoje.year:
            continue
        periodos.append(Periodo(ini, min(fim, (hoje.year, hoje.month)), atual))
    return periodos


def somar_meses(periodos: list[Periodo]) -> int:
    """Soma o tempo dos períodos sem contar duas vezes os que se sobrepõem."""
    intervalos = sorted((p.inicio[0] * 12 + p.inicio[1], p.inicio[0] * 12 + p.inicio[1] + p.meses) for p in periodos)
    total, atual_ini, atual_fim = 0, None, None
    for ini, fim in intervalos:
        if atual_fim is None or ini > atual_fim:
            if atual_fim is not None:
                total += atual_fim - atual_ini
            atual_ini, atual_fim = ini, fim
        else:
            atual_fim = max(atual_fim, fim)
    if atual_fim is not None:
        total += atual_fim - atual_ini
    return total


# ---------------------------------------------------------------- experiências

_MARCADOR = re.compile(r"^\s*[-•*▪●◦·]")


@dataclass
class Experiencia:
    titulo: str        # cargo / empresa / período (sem os tópicos de atividades)
    detalhes: str      # tudo o que está no bloco, incluindo atividades
    periodos: list[Periodo]
    inicio_texto: int  # posição no currículo, para mostrar a evidência
    na_area: bool = True


def _eh_topico(linha: Linha) -> bool:
    return bool(_MARCADOR.match(linha.texto))


def extrair_experiencias(secoes: Secoes, hoje: date) -> list[Experiencia]:
    linhas = secoes.linhas("experiencia")
    if not linhas:
        # Sem seção de experiência identificada: usa o currículo inteiro, menos formação/cursos.
        excluir = {id(x) for nome in ("formacao", "cursos") for x in secoes.linhas(nome)}
        linhas = [x for x in secoes.todas if id(x) not in excluir]

    indices = [i for i, ln in enumerate(linhas) if _PERIODO.search(ln.normal)]
    experiencias: list[Experiencia] = []
    limite_anterior = 0
    for n, i in enumerate(indices):
        # Cabeçalho: até 2 linhas antes do período que não sejam tópicos de atividade.
        ini = i
        while ini > limite_anterior and i - ini < 2 and not _eh_topico(linhas[ini - 1]):
            ini -= 1
        fim = indices[n + 1] if n + 1 < len(indices) else len(linhas)
        # As linhas de cabeçalho do próximo bloco não pertencem a este.
        if n + 1 < len(indices):
            prox = indices[n + 1]
            while fim > i + 1 and prox - fim < 2 and not _eh_topico(linhas[fim - 1]):
                fim -= 1
        bloco = linhas[ini:fim]
        cabecalho = [ln for ln in linhas[ini : i + 1] if not _eh_topico(ln)]
        experiencias.append(
            Experiencia(
                titulo=" · ".join(ln.texto.strip() for ln in cabecalho),
                detalhes="\n".join(ln.texto for ln in bloco),
                periodos=achar_periodos(linhas[i].normal, hoje),
                inicio_texto=linhas[ini].inicio,
            )
        )
        limite_anterior = fim
    return experiencias


def anos_declarados(texto_normal: str) -> int | None:
    valores = [int(m.group(1)) for m in _ANOS_DECLARADOS.finditer(texto_normal)]
    return max(valores) if valores else None


# ---------------------------------------------------------------- formação

NIVEIS = {
    0: "Sem exigência",
    1: "Técnico",
    2: "Superior (cursando ou completo)",
    3: "Superior completo",
    4: "Pós-graduação / MBA",
}
_POS = re.compile(r"\b(mba|pos[\s-]?graduacao|especializacao|mestrado|doutorado|pos[\s-]?graduado)\b")
_SUPERIOR = re.compile(r"\b(bacharelado|bacharel|graduacao|graduado|licenciatura|tecnologo|tecnologia em|ensino superior|superior completo|faculdade|universidade)\b")
_CURSANDO = re.compile(r"\b(cursando|em andamento|previsao|incompleto|trancado|semestre|periodo)\b")
_TECNICO = re.compile(r"\b(tecnico|curso tecnico)\b")
_CONCLUIDO = re.compile(r"\b(concluido|concluida|completo|completa|formado|formada)\b")


@dataclass
class Formacao:
    nivel: int
    linha: str
    inicio_texto: int


def extrair_formacoes(secoes: Secoes) -> list[Formacao]:
    linhas = secoes.linhas("formacao") or secoes.todas
    achados = []
    for ln in linhas:
        n = ln.normal
        tecnico = bool(_TECNICO.search(n)) and not _SUPERIOR.search(n)
        if _POS.search(n):
            nivel = 2 if _CURSANDO.search(n) else 4
        elif tecnico:
            nivel = 1
        elif _SUPERIOR.search(n):
            nivel = 2 if _CURSANDO.search(n) else 3
        elif secoes.linhas("formacao") and _CURSANDO.search(n):
            nivel = 2
        elif secoes.linhas("formacao") and _CONCLUIDO.search(n):
            nivel = 3
        else:
            continue
        achados.append(Formacao(nivel, ln.texto.strip(), ln.inicio))
    return achados


# ---------------------------------------------------------------- local

_UFS = "AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO"
_CIDADE_UF = re.compile(r"([A-ZÀ-Ú][A-Za-zÀ-ú'.]+(?:[ ]+(?:d[aeo]s?[ ]+)?[A-ZÀ-Ú][A-Za-zÀ-ú'.]+)*)[ ]*[-/,–][ ]*(" + _UFS + r")\b")


def cidade_declarada(texto: str) -> str | None:
    """Cidade - UF que aparece no topo do currículo (endereço do candidato)."""
    topo = "\n".join(texto.split("\n")[:12])
    m = _CIDADE_UF.search(topo)
    return f"{m.group(1)} - {m.group(2)}" if m else None


def cidade_no_texto(cidades: list[str], texto_normal: str) -> str | None:
    for cidade in cidades:
        padrao = compilar(cidade)
        if padrao and padrao.search(texto_normal[:1500]):
            return cidade
    return None
