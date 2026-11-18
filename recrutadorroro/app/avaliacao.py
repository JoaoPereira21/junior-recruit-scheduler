"""Avaliação de um currículo contra os critérios de uma vaga, por regras.

Resultado: situação (Atende / Não atende / Verificar), nota de 0 a 100 e, para cada
critério, o trecho do currículo que justifica a conclusão. A ferramenta ordena e
explica; a decisão é sempre do recrutador.

Nome, idade, gênero, estado civil, foto e endereço completo não entram na avaliação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import analise
from .texto import encontrar, linha_de, mascarar, normalizar, variantes

PESOS = {"obrigatorias": 40, "desejaveis": 20, "experiencia": 20, "formacao": 10, "local": 10}

ATENDE = "Atende"
NAO_ATENDE = "Não atende"
VERIFICAR = "Verificar"


@dataclass
class Vaga:
    titulo: str
    obrigatorias: list[str] = field(default_factory=list)
    desejaveis: list[str] = field(default_factory=list)
    anos_minimos: float = 0
    termos_area: list[str] = field(default_factory=list)
    formacao_minima: int = 0
    cursos: list[str] = field(default_factory=list)
    cidades: list[str] = field(default_factory=list)
    modalidade: str = "presencial"  # presencial | hibrido | remoto


@dataclass
class Item:
    nome: str
    atendido: bool
    evidencia: str = ""


@dataclass
class Criterio:
    nome: str
    peso: int
    pontos: float           # 0..1
    resumo: str
    itens: list[Item] = field(default_factory=list)
    eliminatorio: bool = False
    falhou: bool = False

    @property
    def nota(self) -> int:
        return round(self.pontos * 100)


@dataclass
class Resultado:
    situacao: str
    nota: int
    criterios: list[Criterio]
    motivos: list[str]
    alertas: list[str]
    anos_area: float
    anos_total: float
    anos_declarados: int | None
    nivel_formacao: int
    cidade: str | None
    experiencias: list[analise.Experiencia]

    def criterio(self, nome: str) -> Criterio:
        return next(c for c in self.criterios if c.nome == nome)


def _evidencia(texto: str, inicio: int) -> str:
    return mascarar(linha_de(texto, inicio))


def _avaliar_termos(termos: list[str], texto: str, normal: str) -> list[Item]:
    itens = []
    for termo in termos:
        ocorrencias = encontrar(termo, normal)
        rotulo = " / ".join(variantes(termo))
        evid = _evidencia(texto, ocorrencias[0].inicio) if ocorrencias else ""
        itens.append(Item(rotulo, bool(ocorrencias), evid))
    return itens


def num(valor: float) -> str:
    """Número no formato brasileiro: 8.5 -> '8,5'."""
    return f"{valor:g}".replace(".", ",")


def _anos(meses: int) -> float:
    return round(meses / 12, 1)


def avaliar(vaga: Vaga, texto: str, hoje: date | None = None) -> Resultado:
    hoje = hoje or date.today()
    normal = normalizar(texto)
    secoes = analise.separar_secoes(texto)
    criterios: list[Criterio] = []
    motivos: list[str] = []
    alertas: list[str] = []

    if len(texto.strip()) < 80:
        alertas.append("Quase nenhum texto foi lido do arquivo (PDF escaneado ou imagem?). Avalie manualmente.")

    # --- competências obrigatórias
    if vaga.obrigatorias:
        itens = _avaliar_termos(vaga.obrigatorias, texto, normal)
        ok = sum(i.atendido for i in itens)
        faltam = [i.nome for i in itens if not i.atendido]
        c = Criterio("Competências obrigatórias", PESOS["obrigatorias"], ok / len(itens),
                     f"{ok} de {len(itens)} encontradas", itens, eliminatorio=True, falhou=bool(faltam))
        if faltam:
            motivos.append("Não cita: " + ", ".join(faltam))
        criterios.append(c)

    # --- competências desejáveis
    if vaga.desejaveis:
        itens = _avaliar_termos(vaga.desejaveis, texto, normal)
        ok = sum(i.atendido for i in itens)
        criterios.append(Criterio("Competências desejáveis", PESOS["desejaveis"], ok / len(itens),
                                  f"{ok} de {len(itens)} encontradas", itens))

    # --- experiência
    experiencias = analise.extrair_experiencias(secoes, hoje)
    termos_area = [t for t in vaga.termos_area if t.strip()]
    for exp in experiencias:
        exp.na_area = not termos_area or any(encontrar(t, normalizar(exp.titulo)) for t in termos_area)
    periodos_total = [p for e in experiencias for p in e.periodos]
    periodos_area = [p for e in experiencias if e.na_area for p in e.periodos]
    anos_total = _anos(analise.somar_meses(periodos_total))
    anos_area = _anos(analise.somar_meses(periodos_area))
    declarados = analise.anos_declarados(normal)
    if not periodos_total and declarados is not None:
        anos_area = anos_total = float(declarados)
        alertas.append(f"Sem datas de experiência; usado o tempo declarado no texto ({declarados} anos).")

    itens = [
        Item(f"{exp.titulo or 'Experiência'}", exp.na_area,
             f"{', '.join(p.rotulo() for p in exp.periodos)} · "
             f"{'conta como experiência na área' if exp.na_area else 'fora da área da vaga'}")
        for exp in experiencias
    ]
    rotulo_area = "na área" if termos_area else "no total"
    if vaga.anos_minimos > 0:
        pontos = min(1.0, anos_area / vaga.anos_minimos)
        falhou = anos_area < vaga.anos_minimos
        resumo = f"{num(anos_area)} anos {rotulo_area} (mínimo {num(vaga.anos_minimos)})"
        if falhou:
            motivos.append(f"Experiência {rotulo_area}: {num(anos_area)} anos, abaixo do mínimo de {num(vaga.anos_minimos)}")
    else:
        pontos, falhou = (1.0 if anos_area > 0 else 0.5), False
        resumo = f"{num(anos_area)} anos {rotulo_area}"
    if declarados is not None and periodos_total and abs(declarados - anos_area) >= 2:
        alertas.append(f"O currículo declara {declarados} anos de experiência; pelas datas, {num(anos_area)} anos {rotulo_area}. Confira.")
    if not experiencias and declarados is None:
        alertas.append("Não foram encontradas datas de experiência. Confira o tempo de experiência manualmente.")
    criterios.append(Criterio("Experiência", PESOS["experiencia"], pontos, resumo, itens,
                              eliminatorio=vaga.anos_minimos > 0, falhou=falhou))

    # --- formação
    formacoes = analise.extrair_formacoes(secoes)
    nivel = max((f.nivel for f in formacoes), default=0)
    cursos_ok: list[Item] = []
    if vaga.cursos:
        texto_formacao = "\n".join(f.linha for f in formacoes if f.nivel >= 2)
        normal_formacao = normalizar(texto_formacao)
        cursos_ok = [Item(" / ".join(variantes(c)), True, mascarar(linha_de(texto_formacao, o[0].inicio)))
                     for c in vaga.cursos if (o := encontrar(c, normal_formacao))]
    itens = [Item(analise.NIVEIS.get(f.nivel, ""), f.nivel >= vaga.formacao_minima, mascarar(f.linha)) for f in formacoes]
    if vaga.formacao_minima > 0:
        nivel_ok = nivel >= vaga.formacao_minima
        curso_ok = not vaga.cursos or vaga.formacao_minima < 2 or bool(cursos_ok)
        falhou = not (nivel_ok and curso_ok)
        pontos = 1.0 if not falhou else (0.5 if nivel_ok or nivel == vaga.formacao_minima - 1 else 0.0)
        partes = [f"Encontrado: {analise.NIVEIS[nivel] if nivel else 'nenhuma formação identificada'}"]
        if vaga.cursos and vaga.formacao_minima >= 2:
            partes.append("curso aceito: " + (", ".join(i.nome for i in cursos_ok) if cursos_ok else "não encontrado"))
        resumo = "; ".join(partes) + f" (exigido: {analise.NIVEIS[vaga.formacao_minima]})"
        if not nivel_ok:
            motivos.append(f"Formação abaixo do exigido ({analise.NIVEIS[vaga.formacao_minima]})")
        elif not curso_ok:
            motivos.append("Curso não está entre os aceitos: " + ", ".join(" / ".join(variantes(c)) for c in vaga.cursos))
        criterios.append(Criterio("Formação", PESOS["formacao"], pontos, resumo, itens + cursos_ok,
                                  eliminatorio=True, falhou=falhou))
    elif formacoes:
        criterios.append(Criterio("Formação", PESOS["formacao"], 1.0,
                                  f"Encontrado: {analise.NIVEIS.get(nivel, '')} (sem exigência)", itens))

    # --- local (nunca elimina: só alerta, porque região metropolitana e mudança são comuns)
    cidade = analise.cidade_declarada(texto)
    if vaga.modalidade != "remoto" and vaga.cidades:
        achada = analise.cidade_no_texto(vaga.cidades, normal)
        pontos = 1.0 if achada else 0.0
        resumo = f"Local no currículo: {cidade or 'não informado'}"
        if not achada:
            alertas.append(f"Vaga {vaga.modalidade} em {', '.join(vaga.cidades)}; currículo indica {cidade or 'local não informado'}. Verifique disponibilidade.")
        criterios.append(Criterio("Localização", PESOS["local"], pontos, resumo,
                                  [Item(c, analise.cidade_no_texto([c], normal) is not None) for c in vaga.cidades]))

    peso_total = sum(c.peso for c in criterios) or 1
    nota = round(sum(c.pontos * c.peso for c in criterios) / peso_total * 100)

    if any(c.eliminatorio and c.falhou for c in criterios):
        situacao = NAO_ATENDE
    elif alertas:
        situacao = VERIFICAR
    else:
        situacao = ATENDE

    return Resultado(situacao, nota, criterios, motivos, alertas, anos_area, anos_total,
                     declarados, nivel, cidade, experiencias)


ORDEM_SITUACAO = {ATENDE: 0, VERIFICAR: 1, NAO_ATENDE: 2}


def chave_ranking(resultado: Resultado) -> tuple[int, int]:
    return (ORDEM_SITUACAO[resultado.situacao], -resultado.nota)
