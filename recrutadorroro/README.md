# RecrutadorRORO

Triagem de currículos por regras, com tela web, em português. Você cadastra a vaga com
os critérios, envia os currículos (PDF, Word ou TXT) e recebe um ranking com:

- **Situação:** Atende, Verificar ou Não atende;
- **Nota de 0 a 100**;
- **o trecho do currículo** que justifica cada critério, para conferir antes de decidir.

Também dá para **buscar perfis** em todos os currículos já recebidos, de qualquer vaga.
Assim, um candidato que não serviu para uma vaga pode ser encontrado para outra.

Não usa inteligência artificial nem envia dados para fora: tudo roda no seu computador.

## Como executar

Requisito: Python 3.10 ou mais novo.

```bash
cd recrutadorroro
./run.sh
```

Abra <http://127.0.0.1:8000>. O `run.sh` cria o ambiente Python na primeira vez e
instala as dependências.

Para ver um exemplo pronto com 5 currículos **fictícios**:

```bash
.venv/bin/python -m app.exemplo
```

### Passo a passo manual (Windows ou sem o run.sh)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### Testes

```bash
.venv/bin/python -m pytest -q
```

## Como a avaliação funciona

| Critério | Peso | Elimina? | Como é verificado |
|---|---|---|---|
| Competências obrigatórias | 40 | Sim, se faltar qualquer uma | O termo (ou um sinônimo) aparece no currículo |
| Competências desejáveis | 20 | Não | Idem; só aumentam a nota |
| Experiência | 20 | Sim, se abaixo do mínimo | Soma dos períodos (ex.: `2018 - 2021`, `jan/2019 a atual`) sem contar sobreposição. Se a vaga tiver “palavras da área”, só contam empregos cujo cargo cite uma delas |
| Formação | 10 | Sim, se abaixo do mínimo | Nível (técnico, superior cursando/completo, pós) e curso aceito |
| Localização | 10 | **Não**, só gera alerta | Cidade da vaga aparece no topo do currículo |

Quando um critério não tem nada configurado, ele fica de fora e o peso dos outros é recalculado.

- **Não atende:** falhou em algum critério obrigatório. O motivo aparece na tela.
- **Verificar:** atende os obrigatórios, mas há algo para conferir. Por exemplo: cidade
  diferente, tempo declarado diferente do tempo pelas datas, ou PDF sem texto (escaneado).
- **Atende:** cumpre todos os critérios e não há alertas.

O ranking mostra primeiro quem atende, depois quem precisa ser verificado e por último
quem não atende. Dentro de cada grupo, a ordem é pela nota.

### Dicas para escrever os critérios

- Um item por linha. Use `|` para sinônimos: `TOTVS RM | Senior | Protheus`.
- Maiúsculas, acentos, hífens e espaços são ignorados: `eSocial` encontra “e-Social”
  e “E Social”; `DCTFWeb` encontra “DCTF Web”.
- Coloque como obrigatório só o que é realmente eliminatório. Quem não escreve uma
  competência no currículo é marcado como “Não atende”, mesmo que tenha a competência.
- Ao editar os critérios, todos os currículos da vaga são reavaliados na hora.

## Limitações (leia antes de usar)

- **É busca por palavras, não entendimento.** “Fechamento de folha” não é a mesma
  coisa que “folha de pagamento” para a ferramenta, a não ser que você cadastre os dois
  como sinônimos. Confira sempre os candidatos marcados como “Não atende” por
  competência faltando.
- **As datas são lidas por padrões comuns.** Currículos com layout muito diferente
  (colunas, tabelas, imagens) podem ter o tempo de experiência calculado errado. O
  detalhamento mostra quais períodos foram encontrados.
- **PDF escaneado (imagem) não tem texto.** O sistema avisa e o currículo deve ser
  avaliado manualmente.
- **A decisão é sempre do recrutador.** A ferramenta ordena e explica; não reprova
  ninguém sozinha (LGPD, art. 20).

## Privacidade (LGPD)

- Guarda **só o texto** extraído do currículo, nunca o arquivo original, num banco
  local em `dados/recrutador.db`. Essa pasta está no `.gitignore`: **nunca envie para o GitHub**.
- E-mail, telefone, CPF e links pessoais aparecem ocultos na tela.
- Nome, idade, gênero, estado civil e foto **não entram na nota**.
- Exclua a vaga quando o processo seletivo terminar: todos os currículos dela são apagados.
- Para usar em rede (mais de uma pessoa), defina usuário e senha:
  `RECRUTADOR_USUARIO=rh RECRUTADOR_SENHA=uma-senha-forte ./run.sh`, use HTTPS e
  confirme com a TI onde a aplicação pode rodar.
- Para mudar o local do banco: `RECRUTADOR_DB=/caminho/recrutador.db`.

## Estrutura

```
recrutadorroro/
├── app/
│   ├── main.py        # rotas da aplicação web (FastAPI)
│   ├── avaliacao.py   # critérios, pesos, nota e situação
│   ├── analise.py     # leitura do currículo: seções, períodos, formação, cidade
│   ├── texto.py       # normalização, busca de termos e mascaramento de dados pessoais
│   ├── extracao.py    # texto de PDF, DOCX e TXT
│   ├── busca.py       # busca de perfis em todos os currículos
│   ├── db.py          # banco SQLite local
│   ├── exemplo.py     # carrega a vaga e os currículos de exemplo
│   ├── templates/     # telas (HTML)
│   └── static/        # estilo (CSS)
├── exemplos/curriculos/   # currículos FICTÍCIOS para teste
└── tests/
```

## Próximos passos possíveis

- Avaliação com IA (Claude) como segunda opinião, mantendo as regras como filtro
  barato. Exige chave de API e aprovação da empresa para dados pessoais.
- Leitura de PDF escaneado (OCR).
- Importar currículos direto do e-mail ou de um ATS (Gupy etc.).
