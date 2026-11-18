"""RecrutadorRORO: triagem de currículos por regras, com tela web.

Executar:  uvicorn app.main:app --port 8000   (dentro da pasta recrutadorroro)
"""

from __future__ import annotations

import base64
import csv
import io
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from . import db
from .analise import NIVEIS
from .avaliacao import ATENDE, NAO_ATENDE, VERIFICAR, avaliar, chave_ranking, num
from .busca import buscar
from .extracao import ArquivoInvalido, extrair_texto
from .texto import mascarar

PASTA = Path(__file__).resolve().parent
MAX_ARQUIVOS = 200
MAX_MB = 5
MODALIDADES = {"presencial": "Presencial", "hibrido": "Híbrido", "remoto": "Remoto"}
DECISOES = {"pendente": "Pendente", "entrevistar": "Entrevistar", "reprovado": "Reprovado"}

app = FastAPI(title="RecrutadorRORO", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
templates = Jinja2Templates(directory=PASTA / "templates")
templates.env.filters["num"] = num
templates.env.globals.update(
    NIVEIS=NIVEIS, MODALIDADES=MODALIDADES, DECISOES=DECISOES,
    ATENDE=ATENDE, NAO_ATENDE=NAO_ATENDE, VERIFICAR=VERIFICAR,
)


# ---------------------------------------------------------------- acesso (opcional)

@app.middleware("http")
async def senha_opcional(request: Request, call_next):
    """Se RECRUTADOR_USUARIO e RECRUTADOR_SENHA estiverem definidos, exige login."""
    usuario, senha = os.environ.get("RECRUTADOR_USUARIO"), os.environ.get("RECRUTADOR_SENHA")
    if usuario and senha:
        cabecalho = request.headers.get("authorization", "")
        ok = False
        if cabecalho.lower().startswith("basic "):
            try:
                u, _, s = base64.b64decode(cabecalho[6:]).decode().partition(":")
                ok = secrets.compare_digest(u, usuario) and secrets.compare_digest(s, senha)
            except Exception:
                ok = False
        if not ok:
            return Response("Acesso restrito", 401, {"WWW-Authenticate": 'Basic realm="RecrutadorRORO"'})
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return resposta


# ---------------------------------------------------------------- utilitários

def _vaga_ou_404(vaga_id: int):
    linha = db.vaga(vaga_id)
    if linha is None:
        raise HTTPException(404, "Vaga não encontrada")
    return linha


def _ler_formulario_vaga(form) -> tuple[dict, list[str]]:
    erros = []
    dados = {
        "titulo": (form.get("titulo") or "").strip(),
        "descricao": (form.get("descricao") or "").strip(),
        "modalidade": form.get("modalidade") or "presencial",
    }
    for campo in db.CAMPOS_LISTA:
        dados[campo] = "\n".join(db.lista(form.get(campo) or ""))
    if not dados["titulo"]:
        erros.append("Informe o título da vaga.")
    try:
        dados["anos_minimos"] = max(0.0, float((form.get("anos_minimos") or "0").replace(",", ".")))
    except ValueError:
        erros.append("Anos mínimos de experiência deve ser um número.")
        dados["anos_minimos"] = 0.0
    try:
        dados["formacao_minima"] = int(form.get("formacao_minima") or 0)
        if dados["formacao_minima"] not in NIVEIS:
            raise ValueError
    except ValueError:
        erros.append("Escolha uma formação mínima válida.")
        dados["formacao_minima"] = 0
    if dados["modalidade"] not in MODALIDADES:
        erros.append("Escolha uma modalidade válida.")
        dados["modalidade"] = "presencial"
    if not dados["obrigatorias"] and not dados["desejaveis"]:
        erros.append("Informe ao menos uma competência obrigatória ou desejável.")
    return dados, erros


def _ranking(vaga_linha):
    vaga = db.para_vaga(vaga_linha)
    linhas = []
    for c in db.candidatos(vaga_linha["id"]):
        linhas.append((c, avaliar(vaga, c["texto"])))
    linhas.sort(key=lambda par: chave_ranking(par[1]))
    return linhas


# ---------------------------------------------------------------- páginas

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return templates.TemplateResponse(request, "inicio.html", {"vagas": db.vagas()})


@app.get("/vagas/nova", response_class=HTMLResponse)
def nova_vaga(request: Request):
    return templates.TemplateResponse(request, "vaga_form.html", {"vaga": None, "dados": {}, "erros": []})


@app.post("/vagas", response_class=HTMLResponse)
async def criar_vaga(request: Request):
    dados, erros = _ler_formulario_vaga(await request.form())
    if erros:
        return templates.TemplateResponse(request, "vaga_form.html", {"vaga": None, "dados": dados, "erros": erros}, 400)
    vaga_id = db.salvar_vaga(dados)
    return RedirectResponse(f"/vagas/{vaga_id}", 303)


@app.get("/vagas/{vaga_id}", response_class=HTMLResponse)
def ver_vaga(request: Request, vaga_id: int):
    linha = _vaga_ou_404(vaga_id)
    return templates.TemplateResponse(request, "vaga.html", {"vaga": linha, "ranking": _ranking(linha), "mensagens": [], "erros": []})


@app.get("/vagas/{vaga_id}/editar", response_class=HTMLResponse)
def editar_vaga(request: Request, vaga_id: int):
    linha = _vaga_ou_404(vaga_id)
    return templates.TemplateResponse(request, "vaga_form.html", {"vaga": linha, "dados": dict(linha), "erros": []})


@app.post("/vagas/{vaga_id}/editar", response_class=HTMLResponse)
async def salvar_edicao(request: Request, vaga_id: int):
    linha = _vaga_ou_404(vaga_id)
    dados, erros = _ler_formulario_vaga(await request.form())
    if erros:
        return templates.TemplateResponse(request, "vaga_form.html", {"vaga": linha, "dados": dados, "erros": erros}, 400)
    db.salvar_vaga(dados, vaga_id)
    return RedirectResponse(f"/vagas/{vaga_id}", 303)


@app.post("/vagas/{vaga_id}/excluir")
def excluir_vaga(vaga_id: int):
    _vaga_ou_404(vaga_id)
    db.excluir_vaga(vaga_id)
    return RedirectResponse("/", 303)


@app.post("/vagas/{vaga_id}/curriculos", response_class=HTMLResponse)
async def enviar_curriculos(request: Request, vaga_id: int):
    linha = _vaga_ou_404(vaga_id)
    form = await request.form()
    arquivos = [a for a in form.getlist("arquivos") if isinstance(a, UploadFile) and a.filename]
    mensagens, erros = [], []
    if not arquivos:
        erros.append("Selecione ao menos um arquivo.")
    if len(arquivos) > MAX_ARQUIVOS:
        erros.append(f"Envie no máximo {MAX_ARQUIVOS} arquivos por vez.")
        arquivos = []
    novos = repetidos = 0
    for arquivo in arquivos:
        nome = Path(arquivo.filename).name
        conteudo = await arquivo.read(MAX_MB * 1024 * 1024 + 1)
        if len(conteudo) > MAX_MB * 1024 * 1024:
            erros.append(f"{nome}: maior que {MAX_MB} MB.")
            continue
        try:
            texto = extrair_texto(nome, conteudo)
        except ArquivoInvalido as erro:
            erros.append(str(erro))
            continue
        if db.adicionar_candidato(vaga_id, nome, texto):
            novos += 1
        else:
            repetidos += 1
    if novos:
        mensagens.append(f"{novos} currículo(s) adicionado(s) e avaliado(s).")
    if repetidos:
        mensagens.append(f"{repetidos} currículo(s) já estavam nesta vaga e foram ignorados.")
    return templates.TemplateResponse(
        request, "vaga.html",
        {"vaga": linha, "ranking": _ranking(linha), "mensagens": mensagens, "erros": erros},
        400 if erros and not novos else 200,
    )


@app.get("/vagas/{vaga_id}/candidatos/{candidato_id}", response_class=HTMLResponse)
def ver_candidato(request: Request, vaga_id: int, candidato_id: int):
    linha = _vaga_ou_404(vaga_id)
    c = db.candidato(vaga_id, candidato_id)
    if c is None:
        raise HTTPException(404, "Candidato não encontrado")
    ranking = _ranking(linha)
    posicao = next(i for i, (x, _) in enumerate(ranking, 1) if x["id"] == candidato_id)
    resultado = ranking[posicao - 1][1]
    return templates.TemplateResponse(request, "candidato.html", {
        "vaga": linha, "c": c, "r": resultado, "posicao": posicao, "total": len(ranking),
        "texto": mascarar(c["texto"]),
    })


@app.post("/vagas/{vaga_id}/candidatos/{candidato_id}/decisao")
async def decidir(request: Request, vaga_id: int, candidato_id: int):
    form = await request.form()
    if db.candidato(vaga_id, candidato_id) is None:
        raise HTTPException(404, "Candidato não encontrado")
    decisao = form.get("decisao") or ""
    if decisao not in DECISOES:
        raise HTTPException(400, "Decisão inválida")
    db.decidir(vaga_id, candidato_id, decisao, form.get("observacao") or "")
    destino = form.get("voltar") or f"/vagas/{vaga_id}"
    if not destino.startswith(f"/vagas/{vaga_id}"):
        destino = f"/vagas/{vaga_id}"
    return RedirectResponse(destino, 303)


@app.post("/vagas/{vaga_id}/candidatos/{candidato_id}/excluir")
def excluir_candidato(vaga_id: int, candidato_id: int):
    db.excluir_candidato(vaga_id, candidato_id)
    return RedirectResponse(f"/vagas/{vaga_id}", 303)


@app.get("/vagas/{vaga_id}/exportar.csv")
def exportar(vaga_id: int):
    linha = _vaga_ou_404(vaga_id)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(["Posição", "Arquivo", "Situação", "Nota", "Anos na área", "Formação",
                       "Obrigatórias", "Motivos", "Alertas", "Decisão", "Observação"])
    for i, (c, r) in enumerate(_ranking(linha), 1):
        obrig = next((cr.resumo for cr in r.criterios if cr.nome == "Competências obrigatórias"), "")
        escritor.writerow([i, c["arquivo"], r.situacao, r.nota, num(r.anos_area),
                           NIVEIS.get(r.nivel_formacao, ""), obrig, " | ".join(r.motivos),
                           " | ".join(r.alertas), DECISOES.get(c["decisao"], c["decisao"]), c["observacao"]])
    nome = f"ranking_vaga_{vaga_id}.csv"
    # BOM para o Excel abrir com acentos corretos.
    return Response("﻿" + saida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/busca", response_class=HTMLResponse)
def busca(request: Request, q: str = ""):
    termos, perfis = buscar(q, db.todos_candidatos()) if q.strip() else ([], [])
    return templates.TemplateResponse(request, "busca.html", {"q": q, "termos": termos, "perfis": perfis})
