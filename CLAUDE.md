<!-- FLEET:ESTILO-RESPOSTA v1 (2026-09-14) — cópia-mestra: scanners-commons/08-ESTILO-RESPOSTA.md. Editar LÁ e replicar; não divergir nesta cópia. -->
> **Estilo de resposta obrigatório (operador, 2026-09-14): CONCISO — teto de 200 palavras.**
> Toda resposta no chat, nesta ordem: **1) Objetivo** — 1 linha do que foi pedido · **2) O que foi feito** — bullets curtos, cada um com o *porquê* da decisão · **3) Dependências/pendências** — o que falta, o que bloqueia, de quem depende (`nenhuma` quando não houver).
> O teto conta **só prosa**. **Fora do teto** (nunca resumir, cortar nem "amostrar" pra caber): a tabela de entrega gerada pela ferramenta do repo (colada VERBATIM), blocos de comando/código, saída de teste colada como prova e artefato canônico do repo (brief, relatório, análise).
> Sem preâmbulo, sem repetir o pedido, sem recapitular o que já foi dito. Não cabe em 200 palavras? Entregue o essencial dentro do teto e ofereça o detalhe ("quer o detalhe de X?") — nunca estoure em silêncio.

REGRA VIGENTE 2026-09-06: ler ACQUISITION_POLICY.md na raiz. Todos os Pokémon e eras por padrão; NM/LP com referências próprias, EX-NM em revisão sem preço presumido; entrega completa. Substitui regras históricas conflitantes abaixo.

> **Regra vigente de entrega:** [DELIVERY_CHAT.md](DELIVERY_CHAT.md). Resultados somente no chat, referência clicável e coleta nova por solicitação; substitui orientações antigas de entrega via GitHub ou preços reutilizados.

# CLAUDE.md — scanner-comc

Instruções para qualquer sessão do Claude Code que trabalhe neste repositório
(inclui uma sessão da nuvem que só clonou o GitHub e não tem a memória local).
O operador é médico, **não-programador**: explique termos técnicos em linguagem
simples e seja preciso ao mesmo tempo.

**Este arquivo é a documentação técnica canônica do projeto.** O `README.md` é
minimalista **de propósito** (release público discreto: título neutro
"price-compare", sem citar COMC/Pokémon) e aponta de volta pra cá. Notas de
sessão ficam num `HANDOFF.md` local, fora do repositório (gitignored).

## 🛰️ Convenções da frota (cross-scanner)

> **Manual completo** (repo público): https://github.com/matheuscllm-lgtm/scanners-commons — erros comuns, referências de preço, chaves, GitHub Actions e modelo de entrega de TODOS os scanners. Cópia-mestra local (PC do operador): `C:\Users\mathe\scanners-commons\`.

Invariantes que valem para TODOS os scanners:

- **Piso de relevância R$50 (~US$10)** para cartas avulsas.
- **Só Near Mint** (cartas soltas) — condição por match EXATO `== "NM"`, nunca substring.
- **Nunca inventar preço** — fonte falhou → marca/descarta e segue; jamais fabrica número.
- **Nunca recomendar compra** — o scanner reporta; a decisão de capital é do operador.
- **Entrega = tabela markdown no chat** (nunca XLSX/CSV por padrão), gerada pela ferramenta do repo — nunca montada à mão —, mostrando TODAS as linhas. Coluna `Carta` = nome + número; coluna `Links` = `[oferta](url) · [referência](url)`.
- ⚠️ **Threshold deste scanner = percentual INTEIRO** (`--min-discount 20`, env `MIN_DISCOUNT_PERCENT`), como MYP/Liga/eBay. (Até a v0.2 era fração `0.30`; mudou na consolidação de 2026-09-02.)
- **Sem check-ins automáticos de PR** (operador, 2026-09-12): depois de abrir um PR, a sessão reporta o link no chat e **para** — sem `subscribe_pr_activity`, sem check-in agendado (`send_later`/Routine/cron), sem poll de CI/review. Assinatura de PR criada pelo harness deve ser cancelada. Exceção única: pedido explícito do operador ("acompanha esse PR").

Erros recorrentes (3 famílias — detalhe no manual):

1. **Segredo/ambiente:** BOM/zero-width numa chave → crash. `config.clean_secret` remove.
2. **Git:** `main` local defasado por squash-merge PARECE pendência; teste real = `git diff --stat origin/main <branch>` vazio.
3. **Honestidade de preço:** inflação de referência, fallback tratado como real, NM frouxo → sempre validar versão/condição e rotular fallback.

## O que este projeto é (v0.5.0, scanner ÚNICO + modo grading)

Scanner de arbitragem da **COMC** para cartas de Pokémon, num único fluxo:

```
COMC (set-path browse, 2 passadas por set: cartas soltas + slabs)
 → filtros explícitos de set, idioma, condição e certificadora+nota
 → todos os Pokémon por padrão; lista icônica/chase são filtros opcionais
 → identificar a carta (matcher: set + número + total do set + nome; confiança 0-1)
 → referência de preço:  raw NM    = TCGplayer market (tcgcsv → fallback TCGdex)
                         raw EX-NM = SEM preço (revisão à parte, política 2026-09-06)
                         raw LP       = mediana de ≥3 vendas "LP" da mesma carta (PriceCharting)
                         slab         = mediana de vendas da MESMA certificadora+nota+variante
 → desconto = (ref − COMC)/ref ≥ MIN_DISCOUNT_PERCENT (20)
 → status OK / MATCH_REVIEW → ranking (ROI bruto → desconto → spread → popularidade)
 → results/comc_deals_<escopo>_latest.json → comc_summary.py (tabela modelo MYP)
```

- **Raw** = condição por igualdade: só `NM`, em todas as eras — contra o TCGplayer
  market. **EX-NM** nunca recebe preço NM/LP por presunção: vai para a seção "revisão
  sem referência" (política 2026-09-06; `ERA_VINTAGE_MAX_YEAR` só rotula a era). **LP** entra SÓ com
  referência LP: mediana de ≥3 vendas concluídas cujo título diga `LP`/`Lightly Played`
  (sem nota, sem outra condição, mesma variante); pré-filtro seguro antes da consulta:
  `preço COMC ≤ ref NM × (1 − desconto mín.)` (o NM é só TETO, nunca a comparação);
  sem amostra → `lp_no_reference`. **Nunca comparar LP com NM.** `LP_WITH_REFERENCE=false` desliga.
- **Slab** = só notas da allowlist `GRADED_ALLOW` (default PSA 8/9/10, CGC 9/9.5/10 Gem/
  10 Pristine, BGS 9/9.5/10/10 Black Label, SGC 9/9.5/10, TAG 9.5/10). Um slab NUNCA é
  comparado com preço de carta solta. **Referência = mediana de vendas concluídas** (eBay
  via PriceCharting) da MESMA carta, variante, idioma, certificadora, nota e subcategoria
  (BGS 10 Black ≠ BGS 10; CGC 10 Pristine ≠ Gem Mint; TAG 10 ≠ TAG 9.5) — título cita
  SÓ essa nota e o mesmo conjunto de tokens de variante (reverse, 1st, shadowless…).
  Janelas: ≥3 vendas em 180 d → referência válida (`OK`); ≥3 só em 365 d → válida com
  nota `baixa-liquidez(365d)`; 1–2 vendas → `MATCH_REVIEW · vendas<3`; 0 → sem
  referência, sem oportunidade (`slab_no_reference`). **Colunas do PriceCharting (mesmo
  "PSA 10") e buckets genéricos ("Grade 9") NUNCA geram referência** — a coluna exata só
  entra como sanidade (`coluna÷vendas` → MATCH_REVIEW se >30% longe da mediana).
  Nota vizinha/variante diferente nunca é proxy. JP/CN/KR ficam para uma fase à parte
  (só comparáveis com vendas do mesmo idioma).
- **Fonte falhou ≠ sem venda**: rede/bloqueio/página sem tabelas no PriceCharting vira
  `PcError` → contador `Slabs com ERRO na fonte` (nunca "sem referência"); 5 falhas
  seguidas suspendem a passada de slabs no run; página de bloqueio/vazia NUNCA entra no
  cache do dia. Erro interno numa listagem é contado (`listing_errors`) e pulado; o JSON
  `_latest` é gravado SEMPRE (`finally`), e em `--group all` um grupo quebrado não
  cancela os seguintes.
- **Só dados do dia**: sem cursor de retomada; snapshot tcgcsv re-baixado a cada run;
  cache PriceCharting em `.cache/pc/<AAAA-MM-DD>/`. Cada run começa do zero.
- Roda **grátis**, no PC do operador, via Chrome real **headful** (patchright resolve o
  Cloudflare Turnstile; headless NUNCA fura). Recorrência **manual**.

## 🎓 Modo grading (`scan --grading`, operador 2026-11-16)

**Tese do operador:** na COMC a melhor chance de ganho não é a arbitragem, é achar
carta solta em bom estado, de Pokémon desejado, com pouca oferta e muita procura, e
mandar graduar. **Teto de US$100 por carta, SEM piso de preço** (exceção explícita ao
piso de US$10 da frota, só neste modo): o preço é um teto; quem seleciona são os outros
filtros.

```
COMC (só a passada de cartas soltas, condição NM exata)
 → identificar a carta (mesmo matcher) → SEM crivo de desconto
 → PriceCharting, página da VARIANTE exata (comum / reverse / 1st / shadowless):
     referência da nota máxima e da 2ª nota = mediana de vendas da mesma
     certificadora+nota+variante (regra dos slabs) · censo de população · volume
 → a conta:  custo = COMC + custo de graduar
             empate% = (custo − valor cru) / (nota máxima − valor cru)
             valor esperado = taxa10 × nota máx + taxa9 × 2ª nota + resto × cru − custo
 → pontos 0–100 (Pokémon 25 + escassez 25 + procura 25 + economia 25) → ranking
 → results/comc_deals_grading_<escopo>_latest.json → comc_summary.py (tabela própria)
```

- **Rotas** (`--grader`): `PSA` (PSA 10 / PSA 9, custo padrão US$59) e `CGC` (CGC 10 Gem
  Mint / CGC 9.5, custo padrão US$10). `--grading-cost` / `GRADING_COST_USD` trocam o
  custo por carta (ponha aí serviço + frete rateado). Valores **brutos**: sem taxa de
  venda nem imposto.
- **Página da variante exata** (`pricecharting_client.choose_variant_path`): reverse,
  1st edition e shadowless têm página, censo e vendas PRÓPRIOS. Exemplo real
  (2026-11-16, Charmander #9 de Evolutions): comum = 985 PSA 10 em 3.055 graduadas,
  PSA 10 a US$116; reverse = 754 em 5.174, PSA 10 a US$603. Variante sem página
  reconhecida (staff, prerelease, cosmos, erro…) → `grading_no_page`; nunca usa a
  página da carta comum.
- **Saídas do funil**: fonte falhou (`grading_pc_error`), sem página
  (`grading_no_page`), nota máxima sem venda comparável (`grading_no_top_reference`)
  e nota máxima que não paga o custo (`grading_top_below_cost`). O resto entra na
  tabela.
- **Status**: `OK` = carta identificada (confiança ≥ 0.90), valor cru `market`, nota
  máxima com ≥3 vendas, censo utilizável e valor esperado ≥ 0. `MATCH_REVIEW` com
  motivo: `confiança<x`, `cru:mid|low`, `vendas<3(n=…)`, `censo: <motivo>`,
  `censo-CGC-aproximado`, `VE<0`, `retorno-extremo(≥300%)`. Notas que não mudam o
  status: `baixa-liquidez(365d)`, `2ª-nota-sem-ref`.
- **Limites declarados na entrega (não esconder):** a taxa do censo é HISTÓRICA (quem
  gradua escolhe as melhores cópias — não é a chance desta cópia; a conferência do
  scan frente/verso é do operador); o censo é o do PriceCharting, MENSAL, e atrasa em
  set recente (o `pokemon-longterm-outlook` usa a GemRate, diária — portar é
  pendência); o censo CGC não separa 9.5/Pristine (rota CGC vai sempre para revisão);
  a pontuação é régua de ordenação, não previsão.
- **Custo de tempo**: 1 busca + 1 página do PriceCharting por carta identificada
  (~3 s cada; uma página de 96 anúncios levou ~4 min na prova de 2026-11-16).
  Restrinja com `--group`/`--sets`, `--iconic-only`, `--chase-only`, `--max-selected`.
- **Sets sem página no PriceCharting por nome**: `XY Base Set`, `SM Base Set`,
  `Pokemon GO` e os subsets (Trainer Gallery, Shiny Vault, Radiant Collection,
  Galarian Gallery) ainda não casam o console — saem em `grading_no_page`. A v0.5.0
  corrigiu os sets `XY - …`/`SM - …` (ver CHANGELOG).

```bash
python -m comc_scanner scan --group 9 --grading                    # PSA, teto US$100, sem piso
python -m comc_scanner scan --sets "XY - Evolutions" --grading --iconic-only
python -m comc_scanner scan --group 11 --grading --grader CGC --grading-cost 12
python comc_summary.py results/comc_deals_grading_grupo9_latest.json -o results/comc-grading-grupo9-<data>.md --group 9
```

Colunas da tabela do modo grading: `# | Pontos | Retorno esperado% | Custo$ | COMC$ |
Nota máx$ | 2ª nota$ | Crua$ | Taxa nota máx% | Empate% | Pop nota máx/total |
Vendas/mês | Cópias COMC | Pokémon | Carta | Set | Tipo | Ref | Conf | Status | Links`
— fonte única em `reporter.render_grading_table`; valor ausente sai como `n/d`.

## 📤 COMO ENTREGAR RESULTADOS (regra dura — não improvisar)

1. **Entrega = uma tabela markdown colada AQUI no chat.** Nunca arquivo por padrão.
2. **Sai da ferramenta `comc_summary.py` — NUNCA monte tabela à mão:**
   ```bash
   python comc_summary.py results/comc_deals_grupo<N>_latest.json -o results/comc-grupo<N>-<data>.md --group <N>
   ```
   Cole o `.md` **VERBATIM**. Ele traz cabeçalho (contagens, limiares, slabs aceitos,
   **funil** do scan) e DUAS seções — 🟢 **OK** e ⚠️ **MATCH_REVIEW** (validar
   manualmente) — ambas na ordem do ranking. A formatação de linha tem UMA fonte:
   `comc_scanner/reporter.py` (`render_rows_table`/`render_row_line`/`classify_row`).
3. **Mostre TODAS as linhas.**
4. Colunas: `# | Desconto% | ROI bruto% | COMC$ | Ref$ | Spread$ | Pokémon | Carta | Set | Idioma | Tipo | Ref | Conf | Status | Links`
   (nunca "lucro": Spread$ = ref − COMC bruto, sem taxas; ROI bruto% = spread/COMC)
   - `Tipo` = `Raw NM|LP` (EX-NM só na revisão sem preço) ou a nota (`PSA 10`, `CGC 10 Pristine`, `BGS 10 Black Label`);
   - `Ref` = `TCG market|mid|low` ou `PC vendas <nota|LP> (n=…, mês..mês)`;
   - `Status` = `OK` ou `MATCH_REVIEW · motivos` (confiança <0.90, `preço:mid/low`,
     `vendas<3(n=…)`, `coluna÷vendas`, `TCG÷vendas-raw(m)`, `desconto-extremo(≥N%)`)
     + nota `baixa-liquidez(365d)`;
   - `Links` = `[oferta](COMC) · [referência](página da carta no PriceCharting — raw, LP e slab;
     raw cai no TCGplayer se a carta não tiver página no PC ou se a fonte falhar)`. O PREÇO raw segue o TCGplayer market.
5. **Não recomende comprar.**

## Como rodar

> 🎯 **Skill `scan-comc`** (`.claude/skills/scan-comc/SKILL.md`): ao pedirem pra
> "rodar o COMC", o agente **pergunta qual dos 12 grupos** (ou `all`), roda e entrega
> via `comc_summary.py`.

```bash
pip install -r requirements.txt && playwright install chromium   # 1ª vez
python -m comc_scanner list-groups                               # sem rede
python -m comc_scanner scan --group 1                             # raw + slabs, 20%, todos os Pokémon
python -m comc_scanner scan --group all                           # 12 grupos em sequência (1999-2023)
python -m comc_scanner scan --sets "Base Set,Jungle" --era vintage
python -m comc_scanner scan --sets "SV: Scarlet & Violet 151" --languages ja --grades "PSA 10"
```

Flags do `scan`: `--group N|all` xor `--sets` (igualdade exata do nome/alias/abreviação
do set — nunca substring: `"Base Set"` não pega "Base Set 2"; `"151"` NÃO casa
"SV: Scarlet & Violet 151" — use o nome completo, `"Scarlet & Violet 151"` ou `--group`);
`--era`; `--languages en,ja,…`; `--conditions NM,LP,EX-NM`; `--grades "PSA 10,CGC 10 PRISTINE"`;
`--min-discount 20` (inteiro); `--min-price 10`; `--max-price` (teto de orçamento por
carta, corta antes do PriceCharting); `--max-selected N` (encerra o set após N
listagens dos idiomas selecionados; `--max-english` é alias legado; 0 = todas);
`--raw-only` / `--slabs-only`; `--iconic-only` / `--all-pokemon`; `--chase-only`;
`--min-confidence`; `--max-pages`; `--max-run-seconds`; `--interval`; `--top-n`;
`--grading` (+ `--grader PSA|CGC`, `--grading-cost`) — ver "Modo grading".
Outros subcomandos: `list-groups`, `validate-slugs [--revalidate]`, `warm`, `capture`.
`--headful`/`--restart` são aceitos por compatibilidade e não fazem nada (sempre
headful; sempre do zero).

Configuração por env (`.env.example` lista tudo): `MIN_DISCOUNT_PERCENT`,
`MIN_COMC_PRICE`, `ICONIC_ONLY`, `SCAN_RAW`, `SCAN_SLABS`, `COMC_LANGUAGES`,
`RAW_CONDITIONS`, `GRADED_ALLOW`, `EXTREME_DISCOUNT_PERCENT`, `RAW_PLAUSIBILITY`,
`TCGCSV_FORCE_REFRESH`, `PC_CACHE_DIR`…

## Convenções que não mudam

- **Recorrência é MANUAL** (operador, 2026-06-09): não criar Task Scheduler / cron /
  GitHub Actions de scan. (O workflow `scan.yml` via Firecrawl foi removido na v0.3.)
- **Condição e idioma exatos:** NM usa a referência inglesa do TCGplayer; LP só usa
  vendas explicitamente LP; EX-NM fica sem preço presumido. Idiomas selecionados que
  não sejam inglês aparecem como descoberta sem referência, nunca com margem calculada,
  até existir fonte de vendas concluídas no mesmo idioma.
- **Desconto sobre a referência**: `(ref − COMC)/ref` (`margin.py`), limiar inteiro
  `MIN_DISCOUNT_PERCENT` (default 20). ROI bruto `(ref − COMC)/COMC` e spread US$ vêm de
  `ranking.compute_metrics` e só ordenam. Sem taxas embutidas. **Diagnóstico** (operador):
  `scan --group all --min-price 5 --min-discount 10` + `comc_summary.py … --sensitivity 10,15,20`
  → faixas 10–14,99% e 15–19,99% são diagnóstico, NÃO oportunidade; ≥20% = candidato.
- **Slug de set = path ASCII exato da COMC** (`<ano>/Pokemon_<Série>_-_<Set>_-_Base`, sem
  acento). Slug com acento ou inexistente cai numa **categoria-pai** (o ano inteiro) e
  mistura sets — foi assim com o Neo Revelation antigo (paginação infinita) e com
  `Pokémon_EX_Hidden_Legends`. `validate-slugs` só valida se ≥80% da página 1 for do
  próprio set (`page1_own_share` no catálogo); a guarda de paginação é a segunda rede.
- **Lista de Pokémon fora do código** (`iconic_pokemon.csv`); nada hardcoded.
- **Referência de slab = PriceCharting por nota**; TCGplayer não precifica slab.
- **Sinalização, nunca troca de preço (2026-09-06):** (a) **plausibilidade raw NM** —
  para cada carta solta aprovada, o scanner compara o TCGplayer market com a mediana
  de ≥3 vendas de carta solta da mesma carta/variante no PriceCharting
  (`pricecharting_client.raw_plausibility`; qualquer condição, sem nota — por isso
  NÃO serve de referência financeira); divergência >40% (`RAW_SALES_DEVIATION_MAX`)
  → `MATCH_REVIEW · TCG÷vendas-raw(m)`. Caso real que motivou: Base Set Charizard
  4/102 market US$868 vs vendas US$329. `RAW_PLAUSIBILITY=0` desliga; falha da
  fonte só conta no funil. (b) **desconto extremo** — desconto ≥
  `EXTREME_DISCOUNT_PERCENT` (default 60; 0 desliga) → `MATCH_REVIEW ·
  desconto-extremo`, nunca descartado. Os dois valores viajam no JSON do run e a
  entrega os reusa (`comc_summary.py` nunca reclassifica com outro limiar).

## Testes

```bash
python -m pytest tests/    # 366 testes — offline, sem rede, sem browser
```

`tests/fixtures/` traz páginas REAIS: vitrine ungraded (2026-06-08), duas vitrines
`aGraded` (151 e Base Set, 2026-09-02) e duas páginas + uma busca do PriceCharting
(Charizard ex 151; Charizard 4/102 Base Set com 375 vendas, títulos LP e PSA 8).

## Arquitetura

```
comc_scanner/
  __main__.py            CLI: scan | list-groups | validate-slugs | warm | capture
  config.py              Settings (+ env) — MIN_DISCOUNT_PERCENT, GRADED_ALLOW, ICONIC_ONLY…
  groups.py              os 12 grupos canônicos de sets (SV, WotC, EX, DP/Platinum, HGSS/BW, XY, SM, SWSH)
  comc_set_slugs.json    slugs de set validados na COMC (1999-2023; `validate-slugs` confere ao vivo)
  iconic_pokemon.csv     lista do operador (rank, pokemon, score, sources) — EDITÁVEL
  iconic.py              match por palavra inteira contra a lista
  grading.py             parse da nota do slab (/Graded/<grader>/<nota> + título) + allowlist + coluna PC
  grading_mode.py        modo grading: rotas PSA/CGC, a conta (custo, empate, valor esperado), pontos, status
  comc_scraper.py        navegação COMC via patchright headful; parse de raw E slabs
  pipeline.py            Scanner.run_scan (2 passadas/set) + process_listing (funil único) + FunnelStats
  matcher.py / normalize.py / tcg_index.py   identificação da carta no TCGplayer (confiança 0-1)
  tcgcsv_client.py / tcgdex_client.py        referência raw (market → mid → low; fallback TCGdex)
  pricecharting_client.py                    mediana de vendas comparáveis (slab por nota exata; raw LP) + plausibilidade raw + guardas nome/número/set
  margin.py              desconto (ref − comc)/ref
  ranking.py             métricas (desconto, ROI bruto, spread) + ordem de ranking
  reporter.py            tabela canônica + classify_row (OK/MATCH_REVIEW) + JSON/CSV + funil
  models.py              dataclasses (listing com grade, deal com pokemon/ref_source/status)
comc_summary.py          ENTREGA canônica (JSON → markdown, 2 baldes, funil)
tests/                   suíte offline (fixtures reais)
results/                 saídas (gitignored)
```

## Fluxo de desenvolvimento

- Código = **branch + PR**; nunca push direto na `main`.
- Dados de scan, `.env`, caches e perfis de navegador não entram no repo.
- Versão: **0.5.0** (`pyproject.toml` + `CHANGELOG.md`, 2026-11-16).
