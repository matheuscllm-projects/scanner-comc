"""Modo grading — carta solta NM na COMC como candidata a ser graduada.

Tese do operador (2026-11-16): a melhor chance de ganho na COMC não é a arbitragem de
preço, e sim achar carta solta em bom estado, de Pokémon desejado, com pouca oferta e
muita procura, e mandar graduar. O preço é só um TETO (US$100 por carta, sem piso); a
seleção vem dos outros filtros.

O que este módulo faz (funções puras, sem rede):

1. A conta da graduação (``build_case``)::

       custo total   = preço COMC + custo de graduar
       spread da nota máxima = referência da nota máxima − custo total
       empate %      = (custo total − valor cru) / (nota máxima − valor cru)
                       → chance MÍNIMA de nota máxima para a conta fechar
       valor esperado (VE) = taxa10 × nota máxima + taxa9 × 2ª nota
                             + resto × valor cru − custo total

   As referências das notas são as MESMAS dos slabs: mediana de vendas concluídas da
   mesma carta, variante, certificadora e nota (``pricecharting_client``). O "valor
   cru" é a referência raw NM do scanner (TCGplayer market).

2. A pontuação de 0 a 100 que ordena a tabela (``score``), quatro blocos de 25:
   Pokémon (lista do operador), escassez (quantas notas máximas existem no censo),
   procura (vendas por mês da nota máxima) e economia (VE sobre o custo). Escassez e
   procura usam as MESMAS faixas do ``pokemon-longterm-outlook`` (``scoring.py``).

3. O status da linha (``classify_grading_row``): OK ou REVISAR com os motivos.

Limites que a entrega declara (não esconder):

- ``taxa10``/``taxa9`` são a taxa HISTÓRICA do censo (notas 10 ÷ total graduado da
  carta). Quem manda graduar escolhe as melhores cópias, então a taxa não é a chance
  desta cópia — é só a régua de quão difícil a nota máxima tem sido.
- O censo vem do PriceCharting, é MENSAL e pode atrasar em set recente.
- O VE é um cenário, não um preço: nota abaixo da 2ª vale o valor cru, e 2ª nota sem
  ≥3 vendas comparáveis também entra pelo valor cru (hipóteses conservadoras,
  declaradas na entrega).
- Valores brutos: sem taxa de venda, frete nem imposto além do custo de graduar.
- A pontuação é régua de ORDENAÇÃO, não previsão (as faixas nunca foram validadas
  contra resultado). O scanner reporta; não recomenda compra.
"""
from __future__ import annotations

from dataclasses import dataclass

from .grading import Grade
from .ranking import UNRANKED

# Referência válida (não "thin") = ≥3 vendas comparáveis, como nos slabs.
MIN_COMPARABLE_SALES = 3
# Censo com menos graduadas que isto = página fina/duplicada (guarda do outlook).
POP_TOTAL_MIN_TRUST = 25

# Faixas do pokemon-longterm-outlook (outlook/scoring.py) — mesmas réguas na frota.
SCARCITY_POP_BANDS = ((50, 25), (500, 22), (2000, 18), (5000, 12), (10000, 7))
SCARCITY_FLOOR = 3
DEMAND_SALES_BANDS = ((60.0, 25), (30.0, 20), (5.0, 14), (2.0, 8))
DEMAND_FLOOR = 3
# Pokémon: posição na lista icônica do operador (iconic_pokemon.csv).
POKEMON_RANK_BANDS = ((10, 25), (25, 20), (50, 14), (100, 8))
POKEMON_FLOOR = 3
# Economia: retorno do valor esperado sobre o custo total (%).
ECONOMY_ROI_BANDS = ((100.0, 25), (50.0, 20), (25.0, 14), (0.0, 8))
# Retorno esperado a partir do qual a linha é "boa demais": vai para REVISAR, nunca é
# descartada (mesma ideia do `desconto-extremo` da arbitragem). Caso real que motivou
# (2026-11-16): Eevee 125 reverse de Evolving Skies, PSA 10 a US$2.773 com 16 no censo
# e a PSA 10 valendo ~60× a nota 9 — pode ser venda atípica, não mercado.
EXTREME_EV_ROI_PERCENT = 300.0


@dataclass(frozen=True, slots=True)
class GraderPlan:
    """Rota de graduação: certificadora, as duas notas que pagam e o custo padrão."""
    grader: str
    top: Grade              # nota máxima perseguida
    second: Grade           # nota logo abaixo (o "prêmio de consolação")
    pop_key: str            # chave do censo do PriceCharting ("psa" | "cgc")
    second_pop_index: int   # posição da 2ª nota no censo (nota N → índice N−1)
    default_cost: float     # US$ por carta — ajustar com --grading-cost / GRADING_COST_USD
    census_note: str = ""   # ressalva permanente do censo desta certificadora


GRADER_PLANS: dict[str, GraderPlan] = {
    "PSA": GraderPlan(grader="PSA", top=Grade("PSA", 10.0), second=Grade("PSA", 9.0),
                      pop_key="psa", second_pop_index=8, default_cost=59.0),
    # O censo CGC do PriceCharting tem 10 posições (notas inteiras 1..10): não separa
    # 9.5 de 9 nem Pristine de Gem Mint. A taxa sai aproximada e a linha vai SEMPRE
    # para REVISAR com o motivo `censo-CGC-aproximado`.
    "CGC": GraderPlan(grader="CGC", top=Grade("CGC", 10.0, "GEM"), second=Grade("CGC", 9.5),
                      pop_key="cgc", second_pop_index=8, default_cost=10.0,
                      census_note="censo-CGC-aproximado"),
}
VALID_GRADERS = tuple(GRADER_PLANS)


def plan_for(grader: str) -> GraderPlan:
    key = (grader or "").strip().upper()
    if key not in GRADER_PLANS:
        raise ValueError(f"certificadora sem rota de grading: {grader!r} "
                         f"(use {', '.join(VALID_GRADERS)})")
    return GRADER_PLANS[key]


def effective_cost(plan: GraderPlan, configured: float | None) -> float:
    """Custo de graduar por carta: o configurado (> 0) ou o padrão da rota."""
    return float(configured) if configured and configured > 0 else plan.default_cost


# --- pontos --------------------------------------------------------------------

def pokemon_points(rank: int | None) -> int:
    if rank is None or rank >= UNRANKED or rank <= 0:
        return POKEMON_FLOOR
    for cap, pts in POKEMON_RANK_BANDS:
        if rank <= cap:
            return pts
    return POKEMON_FLOOR


def scarcity_points(pop_top: int) -> int:
    for cap, pts in SCARCITY_POP_BANDS:
        if pop_top <= cap:
            return pts
    return SCARCITY_FLOOR


def demand_points(sales_per_month: float) -> int:
    for floor, pts in DEMAND_SALES_BANDS:
        if sales_per_month >= floor:
            return pts
    return DEMAND_FLOOR


def economy_points(ev_roi_pct: float) -> int:
    for floor, pts in ECONOMY_ROI_BANDS:
        if ev_roi_pct >= floor:
            return pts
    return 0


def census_issue(pop: list[int] | None, sales_per_month: float | None) -> str | None:
    """Motivo para NÃO confiar no censo desta página, ou None (guardas do outlook)."""
    if pop is None:
        return "censo n/d"
    total = sum(pop)
    if total < POP_TOTAL_MIN_TRUST:
        return f"censo fino (total {total})"
    top = pop[9]
    if top == 0:
        return f"nenhuma nota máxima no censo ({total} graduadas)"
    if sales_per_month is not None and sales_per_month > top:
        return f"censo não confiável ({sales_per_month:g} vendas/mês com só {top} no censo)"
    return None


# --- a conta -------------------------------------------------------------------

@dataclass(slots=True)
class GradingCase:
    """A conta de graduar UMA listagem. Só números lidos ou derivados por fórmula."""
    grader: str
    top_label: str
    second_label: str
    grading_cost: float
    comc_price: float
    total_cost: float
    raw_value: float                 # referência raw NM (TCGplayer) — valor "se não vier nota"
    top_price: float                 # mediana de vendas da nota máxima
    top_n_sales: int
    top_liquidity: str               # "ok" | "low" | "thin"
    top_window_days: int
    top_ref_label: str
    second_price: float | None       # mediana da 2ª nota (None = sem venda comparável)
    second_n_sales: int
    second_usable: bool              # True = ≥3 vendas (entra no VE pelo próprio preço)
    spread_top: float                # top_price − total_cost
    spread_second: float | None
    breakeven_pct: float | None      # chance mínima de nota máxima para empatar (%)
    pop_top: int | None
    pop_second: int | None
    pop_total: int | None
    gem_rate_pct: float | None       # taxa histórica da nota máxima no censo (%)
    second_rate_pct: float | None
    pop_issue: str                   # "" = censo utilizável
    census_note: str                 # ressalva permanente da certificadora ("" = nenhuma)
    sales_per_month: float | None
    sales_source: str                # "pc-volume" | "amostra-180d" | ""
    copies: int                      # cópias à venda na COMC (tile "N from")
    ev: float | None                 # valor esperado líquido do custo (US$)
    ev_roi_pct: float | None
    pts_pokemon: int
    pts_scarcity: int
    pts_demand: int
    pts_economy: int

    @property
    def score(self) -> int:
        return self.pts_pokemon + self.pts_scarcity + self.pts_demand + self.pts_economy

    def as_row(self) -> dict[str, object]:
        r2 = lambda v: None if v is None else round(v, 2)  # noqa: E731
        return {
            "mode": "grading",
            "grading_grader": self.grader,
            "grading_top_label": self.top_label,
            "grading_second_label": self.second_label,
            "grading_cost": round(self.grading_cost, 2),
            "grading_total_cost": round(self.total_cost, 2),
            "grading_raw_value": round(self.raw_value, 2),
            "grading_top_price": round(self.top_price, 2),
            "grading_top_n_sales": self.top_n_sales,
            "grading_top_liquidity": self.top_liquidity,
            "grading_top_window_days": self.top_window_days,
            "grading_top_ref_label": self.top_ref_label,
            "grading_second_price": r2(self.second_price),
            "grading_second_n_sales": self.second_n_sales,
            "grading_second_usable": self.second_usable,
            "grading_spread_top": round(self.spread_top, 2),
            "grading_spread_second": r2(self.spread_second),
            "grading_breakeven_pct": r2(self.breakeven_pct),
            "grading_pop_top": self.pop_top,
            "grading_pop_second": self.pop_second,
            "grading_pop_total": self.pop_total,
            "grading_gem_rate_pct": r2(self.gem_rate_pct),
            "grading_second_rate_pct": r2(self.second_rate_pct),
            "grading_pop_issue": self.pop_issue,
            "grading_census_note": self.census_note,
            "grading_sales_per_month": self.sales_per_month,
            "grading_sales_source": self.sales_source,
            "grading_copies": self.copies,
            "grading_ev": r2(self.ev),
            "grading_ev_roi_pct": r2(self.ev_roi_pct),
            "grading_pts_pokemon": self.pts_pokemon,
            "grading_pts_scarcity": self.pts_scarcity,
            "grading_pts_demand": self.pts_demand,
            "grading_pts_economy": self.pts_economy,
            "grading_score": self.score,
        }


def build_case(plan: GraderPlan, snapshot, comc_price: float, raw_value: float,
               grading_cost: float, pokemon_rank: int | None = None,
               copies: int = 1) -> GradingCase | None:
    """Monta a conta a partir do retrato da página (``GradingSnapshot``). Devolve None
    quando não há NENHUMA venda comparável da nota máxima — sem referência não há conta
    (nunca se usa coluna do PriceCharting nem nota vizinha no lugar)."""
    top_ref = snapshot.refs.get(plan.top.key)
    if top_ref is None or not top_ref.price or top_ref.price <= 0:
        return None
    second_ref = snapshot.refs.get(plan.second.key)
    second_price = second_ref.price if second_ref is not None else None
    second_usable = bool(second_ref is not None and second_ref.liquidity in ("ok", "low"))
    raw_value = max(float(raw_value or 0.0), 0.0)
    total_cost = float(comc_price) + float(grading_cost)
    spread_top = top_ref.price - total_cost
    spread_second = (second_price - total_cost) if second_price is not None else None
    breakeven = None
    if top_ref.price > raw_value:
        breakeven = min(100.0, max(0.0, (total_cost - raw_value) / (top_ref.price - raw_value) * 100.0))

    # Procura: volume do próprio PriceCharting (só existe para a PSA 10); senão, a
    # contagem de vendas comparáveis em 180 dias ÷ 6 (a lista da página é limitada a
    # ~30 vendas por nota, então em carta muito líquida isso é um PISO).
    sales_pm, sales_source = None, ""
    if plan.top.key == "PSA 10" and snapshot.psa10_sales_per_month is not None:
        sales_pm, sales_source = snapshot.psa10_sales_per_month, "pc-volume"
    else:
        n180 = int((snapshot.comps_180d or {}).get(plan.top.key, 0) or 0)
        if n180:
            sales_pm, sales_source = round(n180 / 6.0, 1), "amostra-180d"

    pop = (snapshot.pop or {}).get(plan.pop_key) if snapshot.pop else None
    issue = census_issue(pop, sales_pm) or ""
    pop_top = pop_second = pop_total = None
    gem_rate = second_rate = ev = ev_roi = None
    if pop is not None:
        pop_top, pop_second, pop_total = pop[9], pop[plan.second_pop_index], sum(pop)
    if pop is not None and not issue:
        g_top = pop_top / pop_total
        g_second = pop_second / pop_total
        gem_rate, second_rate = g_top * 100.0, g_second * 100.0
        second_value = second_price if (second_usable and second_price is not None) else raw_value
        expected = (g_top * top_ref.price + g_second * second_value
                    + max(0.0, 1.0 - g_top - g_second) * raw_value)
        ev = expected - total_cost
        ev_roi = (ev / total_cost * 100.0) if total_cost > 0 else None

    return GradingCase(
        grader=plan.grader, top_label=plan.top.label, second_label=plan.second.label,
        grading_cost=float(grading_cost), comc_price=float(comc_price), total_cost=total_cost,
        raw_value=raw_value, top_price=float(top_ref.price), top_n_sales=int(top_ref.n_sales),
        top_liquidity=top_ref.liquidity, top_window_days=int(top_ref.window_days),
        top_ref_label=top_ref.label, second_price=second_price,
        second_n_sales=int(second_ref.n_sales) if second_ref is not None else 0,
        second_usable=second_usable, spread_top=spread_top, spread_second=spread_second,
        breakeven_pct=breakeven, pop_top=pop_top, pop_second=pop_second, pop_total=pop_total,
        gem_rate_pct=gem_rate, second_rate_pct=second_rate, pop_issue=issue,
        census_note=plan.census_note, sales_per_month=sales_pm, sales_source=sales_source,
        copies=int(copies or 1), ev=ev, ev_roi_pct=ev_roi,
        pts_pokemon=pokemon_points(pokemon_rank),
        pts_scarcity=scarcity_points(pop_top) if (pop_top is not None and not issue) else 0,
        pts_demand=demand_points(sales_pm) if sales_pm is not None else 0,
        pts_economy=economy_points(ev_roi) if ev_roi is not None else 0,
    )


# --- status e ordenação (lidos da linha plana do JSON) ----------------------------

def _num(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_grading_row(row: dict) -> bool:
    return str(row.get("mode") or "") == "grading"


def classify_grading_row(row: dict, trust: float = 0.90) -> tuple[str, list[str]]:
    """(status, motivos). OK só quando a carta foi identificada com confiança, o valor
    cru é preço 'market' real, a nota máxima tem ≥3 vendas comparáveis, o censo é
    utilizável e o valor esperado não é negativo.

    Motivos de REVISAR:
    - `confiança<x`           — match carta↔catálogo abaixo do limiar do run;
    - `cru:mid|low`           — valor cru veio de fallback do TCGplayer (não é venda);
    - `vendas<3(n=…)`         — nota máxima com só 1–2 vendas comparáveis;
    - `censo: <motivo>`       — censo ausente, fino ou incoerente (sem taxa nem VE);
    - `censo-CGC-aproximado`  — o censo CGC não separa 9.5/Pristine;
    - `VE<0`                  — pela taxa histórica, o valor esperado não paga o custo
                                (a cópia pode ser melhor que a média: conferir o scan);
    - `retorno-extremo(≥N%)`  — retorno esperado ≥ ``EXTREME_EV_ROI_PERCENT``: bom
                                demais, conferir as vendas da nota máxima (nunca descartar)."""
    from .models import STATUS_OK, STATUS_REVIEW  # import tardio (evita ciclo)

    reasons: list[str] = []
    conf = _num(row, "confidence") or 0.0
    if conf < trust:
        reasons.append(f"confiança<{trust:.2f}")
    field = str(row.get("price_field") or "").strip()
    if field and field != "market":
        reasons.append(f"cru:{field}")
    n = _num(row, "grading_top_n_sales")
    if n is not None and n < MIN_COMPARABLE_SALES:
        reasons.append(f"vendas<{MIN_COMPARABLE_SALES}(n={int(n)})")
    issue = str(row.get("grading_pop_issue") or "").strip()
    if issue:
        reasons.append(f"censo: {issue}")
    note = str(row.get("grading_census_note") or "").strip()
    if note:
        reasons.append(note)
    ev = _num(row, "grading_ev")
    if ev is not None and ev < 0:
        reasons.append("VE<0")
    ev_roi = _num(row, "grading_ev_roi_pct")
    if ev_roi is not None and ev_roi >= EXTREME_EV_ROI_PERCENT:
        reasons.append(f"retorno-extremo(≥{int(EXTREME_EV_ROI_PERCENT)}%)")
    return (STATUS_REVIEW if reasons else STATUS_OK), reasons


def grading_row_notes(row: dict) -> list[str]:
    """Notas que NÃO mudam o status: `baixa-liquidez(365d)` (≥3 vendas só em 365 dias)
    e `2ª-nota-sem-ref` (a 2ª nota entrou no VE pelo valor cru, por falta de ≥3 vendas)."""
    notes: list[str] = []
    if str(row.get("grading_top_liquidity") or "") == "low":
        notes.append("baixa-liquidez(365d)")
    if row.get("grading_ev") is not None and not row.get("grading_second_usable"):
        notes.append("2ª-nota-sem-ref")
    return notes


def grading_sort_key(row: dict) -> tuple[float, float, float, int]:
    """Menor = melhor: pontos (0–100) → retorno do valor esperado → spread da nota
    máxima sobre o custo → Pokémon mais procurado."""
    score = _num(row, "grading_score") or 0.0
    ev_roi = _num(row, "grading_ev_roi_pct")
    spread = _num(row, "grading_spread_top") or 0.0
    cost = _num(row, "grading_total_cost") or 0.0
    try:
        rank = int(row.get("pokemon_rank") or UNRANKED)
    except (TypeError, ValueError):
        rank = UNRANKED
    return (-score, -(ev_roi if ev_roi is not None else float("-inf")),
            -(spread / cost if cost > 0 else 0.0), rank)
