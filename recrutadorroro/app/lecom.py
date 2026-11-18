"""Importação de vagas a partir do PDF de solicitação de contratação do Lecom.

Lê apenas os campos da VAGA (job description, cargo, área, senioridade, modelo de
trabalho e código). Os dados pessoais do formulário (solicitante, e-mail, telefone,
diretoria, faturamento, justificativa, pareceres) são ignorados e nunca guardados.

O resultado é uma SUGESTÃO de critérios: a tela mostra o formulário preenchido para o
recrutador revisar antes de salvar.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from .texto import normalizar, preparar

# Todos os rótulos do formulário: servem para delimitar colunas e o fim de cada valor.
_ROTULOS = [
    "Nome do Solicitante:", "E-mail do Solicitante:", "Diretoria:", "Telefone do Solicitante:",
    "Tipo de Solicitação:", "Tipo da Demanda:", "Lecom de Desligamento:", "Tipo de Job Description:",
    "Job Description:", "Squad / Área de Atuação:", "Cargo:", "Perfil / Senioridade:",
    "Período da Contratação:", "Faixa de Faturamento:", "Data Prevista de Início:", "Carga Horária:",
    "Modelo de Trabalho:", "Indicação de Candidato:", "Justificativa de Negócio:", "Parecer:",
    "Responsável Pela Validação Peopleware:", "Data da Validação:",
    "Detalhar Negativa ou Solicitação de Ajuste:", "Detalhamento da Decisão:",
]
# Únicos campos que o importador usa.
_CAMPOS_USADOS = {
    "Squad / Área de Atuação:": "area",
    "Cargo:": "cargo",
    "Perfil / Senioridade:": "senioridade",
    "Modelo de Trabalho:": "modelo",
    "Tipo de Job Description:": "tipo_jd",
}
_SECOES_FORM = ("Parecer da Peopleware", "Parecer da Diretoria", "Dados Gerais da Contratação",
                "Informações do Solicitante")


class NaoEhLecom(ValueError):
    pass


@dataclass
class _Palavra:
    x0: float
    texto: str


@dataclass
class _Linha:
    palavras: list[_Palavra]

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palavras)


def _linhas_pdf(conteudo: bytes) -> list[_Linha]:
    import pdfplumber

    linhas: list[_Linha] = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pagina in pdf.pages:
            atual: list[_Palavra] = []
            topo = None
            for w in sorted(pagina.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
                if topo is not None and abs(w["top"] - topo) > 3:
                    linhas.append(_Linha(sorted(atual, key=lambda p: p.x0)))
                    atual = []
                topo = w["top"] if topo is None or abs(w["top"] - topo) > 3 else topo
                atual.append(_Palavra(w["x0"], w["text"]))
            if atual:
                linhas.append(_Linha(sorted(atual, key=lambda p: p.x0)))
    return linhas


def _rotulos_na_linha(linha: _Linha) -> list[tuple[str, float]]:
    """Rótulos conhecidos presentes na linha, com a posição x onde começam."""
    achados = []
    palavras = linha.palavras
    for rotulo in _ROTULOS:
        partes = rotulo.split()
        for i in range(len(palavras) - len(partes) + 1):
            if [p.texto for p in palavras[i : i + len(partes)]] == partes:
                achados.append((rotulo, palavras[i].x0))
    return sorted(achados, key=lambda a: a[1])


def _campos(linhas: list[_Linha]) -> dict[str, str]:
    """Valor de cada campo usado: as palavras da linha seguinte na mesma coluna do rótulo."""
    campos: dict[str, str] = {}
    for n, linha in enumerate(linhas):
        rotulos = _rotulos_na_linha(linha)
        for k, (rotulo, x0) in enumerate(rotulos):
            chave = _CAMPOS_USADOS.get(rotulo)
            if not chave or chave in campos:
                continue
            x_fim = rotulos[k + 1][1] if k + 1 < len(rotulos) else float("inf")
            valor = []
            for seguinte in linhas[n + 1 : n + 4]:
                if _rotulos_na_linha(seguinte) or seguinte.texto.strip() in _SECOES_FORM:
                    break
                parte = [p.texto for p in seguinte.palavras if x0 - 3 <= p.x0 < x_fim - 3]
                if not parte:
                    break
                valor.append(" ".join(parte))
            campos[chave] = " ".join(valor).strip()
    return campos


def _job_description(texto: str) -> str:
    m = re.search(r"^Job Description:\s*\n(.*?)(?:\nSquad / Área de Atuação:|\nParecer da Peopleware|\Z)", texto, re.S | re.M)
    return m.group(1).strip() if m else ""


def _codigo(texto: str) -> str:
    topo = "\n".join(texto.split("\n")[:4])
    m = re.search(r"\b\d\.\d{3}\.\d{3}\b", topo)
    return m.group(0) if m else ""


# ---------------------------------------------------------------- critérios

_SECOES_JD = {
    "requisitos": ("requisitos", "pre-requisitos", "pre requisitos", "qualificacoes", "o que buscamos",
                   "o que esperamos"),
    "diferenciais": ("diferenciais", "diferencial", "desejaveis", "desejavel", "sera um diferencial",
                     "seria um diferencial"),
    "certificacoes": ("certificacoes", "certificacao"),
    "atividades": ("principais atividades", "atividades", "responsabilidades", "papel", "perfil"),
    "formacao": ("formacao", "escolaridade"),
}
_PREFIXOS = re.compile(
    r"^(principal|projetos de|projeto de|nocoes de|nocao de|conhecimentos? (?:em|de|basicos? em)|"
    r"experiencia (?:comprovada )?(?:em|com)|vivencia (?:em|com)|dominio (?:de|em)|atuacao (?:em|com)|"
    r"testes de)\s*:?\s*",
)
_DESEJAVEL_NA_LINHA = re.compile(r"^(nocoes de|nocao de|conhecimentos? basicos?)")
_SENIORIDADE_ANOS = re.compile(r"(\d{1,2})\s*\+?\s*anos")
_EXPERIENCIA_EM = re.compile(r"experiencia (?:comprovada |solida |previa )?(?:em|com|como) ([^,;.:]+)")
_SENIORIDADES = re.compile(
    r"\b(junior|jr|pleno|pl|senior|sr|especialista|lider|coordenador|gerente|analista|consultor|"
    r"assistente|auxiliar|tecnico|estagiario|trainee|i{1,3}|iv)\b"
)
_MAX_PALAVRAS = 4


@dataclass
class Importacao:
    dados: dict
    avisos: list[str] = field(default_factory=list)
    ignorados: list[str] = field(default_factory=list)
    resumo: list[tuple[str, str]] = field(default_factory=list)


def _secao(normal: str) -> tuple[str, str] | None:
    limpo = normal.strip(" -•*#").strip()
    for secao, nomes in _SECOES_JD.items():
        for nome in nomes:
            if limpo == nome or re.match(re.escape(nome) + r"(\s+[a-z]+)?\s*:", limpo):
                resto = limpo.split(":", 1)[1].strip() if ":" in limpo else ""
                return secao, resto
            if limpo.startswith(nome) and len(limpo) <= len(nome) + 15 and ":" not in limpo:
                return secao, ""
    return None


def _itens(trecho: str, original: str) -> tuple[list[str], list[str]]:
    """Quebra uma linha de requisitos em termos curtos. Devolve (termos, trechos longos)."""
    # índice do texto normalizado == índice do original (mesmo comprimento)
    termos, longos = [], []
    sem_parenteses = re.sub(r"\([^)]*\)", "", original)
    sem_parenteses_n = normalizar(sem_parenteses)
    for parte, parte_n in _partes(sem_parenteses, sem_parenteses_n, r"[,;]|\s+e\s+|\.(?:\s|$)"):
        parte, parte_n = parte.strip(" .:-•*"), parte_n.strip(" .:-•*")
        m = _PREFIXOS.match(parte_n)
        while m and m.end() > 0:
            parte, parte_n = parte[m.end():].strip(), parte_n[m.end():].strip()
            m = _PREFIXOS.match(parte_n)
        if not parte or parte_n in {"com", "e", "ou"}:
            continue
        variantes = [v.strip() for v in re.split(r"\s+ou\s+|/(?=\s)", parte) if v.strip()]
        termo = " | ".join(variantes)
        if len(parte.split()) > _MAX_PALAVRAS * (len(variantes) if len(variantes) > 1 else 1):
            longos.append(parte)
        else:
            termos.append(termo)
    return termos, longos


def _partes(texto: str, normal: str, separador: str):
    inicio = 0
    for m in re.finditer(separador, normal):
        yield texto[inicio : m.start()], normal[inicio : m.start()]
        inicio = m.end()
    yield texto[inicio:], normal[inicio:]


def _sem_duplicados(termos: list[str], ja_usados: set[str]) -> list[str]:
    saida = []
    for t in termos:
        chave = normalizar(t)
        if chave not in ja_usados:
            ja_usados.add(chave)
            saida.append(t)
    return saida


def _titulo(jd: str, cargo: str, senioridade: str) -> str:
    m = re.search(r"^(?:vaga|cargo|posi[cç][aã]o)\s*:\s*(.+)$", jd, re.I | re.M)
    if m:
        return re.sub(r"\s*\(.*$", "", m.group(1)).strip()
    if cargo:
        titulo = cargo.title().replace(" De ", " de ").replace(" Da ", " da ").replace(" Do ", " do ")
        return f"{titulo} {senioridade}".strip() if senioridade and normalizar(senioridade) not in normalizar(titulo) else titulo
    return ""


def _termos_area(titulo: str) -> list[str]:
    """Núcleo do título sem cargo/senioridade: 'Analista SAP BASIS Sênior' -> 'SAP BASIS'."""
    palavras = [p for p in titulo.split() if not _SENIORIDADES.fullmatch(normalizar(p).strip(".,"))]
    while palavras and normalizar(palavras[0]) in {"de", "da", "do", "em"}:
        palavras.pop(0)
    nucleo = " ".join(palavras).strip()
    return [nucleo] if nucleo else []


def interpretar(texto: str, campos: dict[str, str]) -> Importacao:
    jd = _job_description(texto)
    if not jd and "Job Description" not in texto:
        raise NaoEhLecom("Este PDF não parece ser uma solicitação de contratação do Lecom.")

    senioridade = campos.get("senioridade", "")
    titulo = _titulo(jd, campos.get("cargo", ""), senioridade)
    codigo = _codigo(texto)

    obrigatorias: list[str] = []
    desejaveis: list[str] = []
    termos_area: list[str] = []
    ignorados: list[str] = []
    formacao = 0
    anos = 0.0
    secao = None

    for original in jd.split("\n"):
        if not original.strip():
            continue
        normal = normalizar(original)
        achado = _secao(normal)
        if achado:
            secao, resto_n = achado
            if not resto_n:
                continue
            original = original[len(original) - len(resto_n):] if len(resto_n) <= len(original) else original
            normal = normalizar(original)
            if secao == "requisitos":
                for m in _EXPERIENCIA_EM.finditer(normal):
                    alvo = original[m.start(1):m.end(1)].strip()
                    alvo = re.sub(r"\s+(de preferencia|preferencialmente).*$", "", alvo, flags=re.I)
                    if 0 < len(alvo.split()) <= _MAX_PALAVRAS:
                        obrigatorias.append(alvo)
                        termos_area.append(alvo)
                continue
        for m in _SENIORIDADE_ANOS.finditer(normal):
            if secao in ("requisitos", None) and "experiencia" in normal:
                anos = max(anos, float(m.group(1)))
        if secao in ("requisitos", "formacao") and re.search(r"superior|graduac|bacharel|formacao em", normal):
            formacao = max(formacao, 2 if re.search(r"cursando|em andamento", normal) else 3)
        if secao == "certificacoes":
            desejaveis.append("certificação | certificado | certified")
            continue
        if secao == "requisitos":
            termos, longos = _itens(normal, original)
            (desejaveis if _DESEJAVEL_NA_LINHA.match(normal.strip()) else obrigatorias).extend(termos)
            ignorados.extend(longos)
        elif secao == "diferenciais":
            termos, longos = _itens(normal, original)
            desejaveis.extend(termos)
            ignorados.extend(longos)

    usados: set[str] = set()
    obrigatorias = _sem_duplicados(obrigatorias, usados)
    desejaveis = _sem_duplicados(desejaveis, usados)
    termos_area = _sem_duplicados(termos_area, set()) or _termos_area(titulo)

    modelo = normalizar(campos.get("modelo", ""))
    modalidade = "remoto" if "remoto" in modelo else "hibrido" if "hibrido" in modelo else "presencial"

    cabecalho = " · ".join(x for x in [
        f"Lecom {codigo}" if codigo else "",
        f"Área: {campos['area']}" if campos.get("area") else "",
        f"Cargo: {campos['cargo']}" if campos.get("cargo") else "",
        f"Senioridade: {senioridade}" if senioridade else "",
        f"Modelo: {campos['modelo']}" if campos.get("modelo") else "",
    ] if x)
    minimo = 70 if len(obrigatorias) > 6 else 100

    dados = {
        "titulo": f"{titulo} (Lecom {codigo})" if codigo and titulo else titulo,
        "descricao": (cabecalho + "\n\n" + jd).strip(),
        "obrigatorias": "\n".join(obrigatorias),
        "desejaveis": "\n".join(desejaveis),
        "minimo_obrigatorias": minimo,
        "anos_minimos": anos,
        "termos_area": "\n".join(termos_area),
        "formacao_minima": formacao,
        "cursos": "",
        "cidades": "",
        "modalidade": modalidade,
    }

    imp = Importacao(dados, ignorados=ignorados)
    imp.resumo = [(k, v) for k, v in [
        ("Código Lecom", codigo), ("Cargo", campos.get("cargo", "")), ("Área", campos.get("area", "")),
        ("Senioridade", senioridade), ("Modelo de trabalho", campos.get("modelo", "")),
    ] if v]
    if not jd:
        imp.avisos.append("A job description não veio no PDF (talvez esteja em anexo). Preencha os critérios manualmente.")
    if not obrigatorias:
        imp.avisos.append("Nenhum requisito obrigatório foi identificado. Preencha as competências obrigatórias.")
    if minimo < 100:
        imp.avisos.append(
            f"A vaga tem {len(obrigatorias)} requisitos obrigatórios. Para não eliminar bons candidatos que "
            f"não escreveram todos, o mínimo foi sugerido em {minimo}% deles. Ajuste se quiser."
        )
    if not anos:
        texto_senior = f" (senioridade: {senioridade})" if senioridade else ""
        imp.avisos.append(f"A vaga não informa anos de experiência{texto_senior}. Defina o mínimo se quiser usar esse critério.")
    if modalidade != "remoto":
        imp.avisos.append("Vaga não remota: informe a(s) cidade(s) para o alerta de localização.")
    return imp


def importar_pdf(conteudo: bytes) -> Importacao:
    from .extracao import extrair_texto

    texto = extrair_texto("lecom.pdf", conteudo)
    if "Job Description" not in texto:
        raise NaoEhLecom("Este PDF não parece ser uma solicitação de contratação do Lecom (campo “Job Description” não encontrado).")
    return interpretar(preparar(texto), _campos(_linhas_pdf(conteudo)))
