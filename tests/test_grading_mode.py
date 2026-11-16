"""Modo grading (offline): censo + página da variante + conta da graduação + entrega.

Páginas REAIS do PriceCharting capturadas em 2026-11-16 (Charmander #9 de Evolutions):
a comum (985 PSA 10 em 3.055 graduadas) e a reverse holo (754 em 5.174) — o caso que
mostra por que o censo tem de vir da página da variante EXATA. ``_today`` é congelado no
dia da captura para as janelas de recência não envelhecerem."""
import datetime as dt
import json
from pathlib import Path

import pytest

import comc_summary
from comc_scanner import grading_mode as gm
from comc_scanner import pipeline as pl
from comc_scanner import pricecharting_client as pc
from comc_scanner.__main__ import GRADING_DEFAULT_MAX_PRICE, _apply_overrides, build_parser, main
from comc_scanner.config import load_settings
from comc_scanner.models import ComcListing
from comc_scanner.normalize import normalize_set
from comc_scanner.pricecharting_client import GradingSnapshot, SalesRef
from comc_scanner.ranking import sort_rows
from comc_scanner.reporter import render_grading_table
from comc_scanner.tcg_index import TcgIndex

FIX = Path(__file__).parent / "fixtures"
SEARCH = (FIX / "pc_search_charmander_evolutions_9.html").read_text(encoding="utf-8")
PAGE_BASE = (FIX / "pc_product_charmander_evolutions_9.html").read_text(encoding="utf-8")
PAGE_REVERSE = (FIX / "pc_product_charmander_evolutions_reverse_9.html").read_text(encoding="utf-8")
CAPTURE_DAY = dt.date(2026, 11, 16)
SET = "XY - Evolutions"
REVERSE = frozenset({"reverse"})
PSA = gm.GRADER_PLANS["PSA"]
CGC = gm.GRADER_PLANS["CGC"]


@pytest.fixture
def frozen_today(monkeypatch):
    monkeypatch.setattr(pc, "_today", lambda: CAPTURE_DAY)


def _stub_fetch(monkeypatch):
    def fake(url, cache_dir=None):
        if "search-products" in url:
            return SEARCH
        return PAGE_REVERSE if "reverse" in url else PAGE_BASE
    monkeypatch.setattr(pc, "fetch_page", fake)


# --- censo e volume (páginas reais) ------------------------------------------------

def test_pop_report_is_per_variant_page():
    base, rev = pc.parse_pop_report(PAGE_BASE), pc.parse_pop_report(PAGE_REVERSE)
    assert base["psa"][9] == 985 and sum(base["psa"]) == 3055
    assert rev["psa"][9] == 754 and sum(rev["psa"]) == 5174
    assert len(rev["cgc"]) == 10 and rev["cgc"][9] == 70


@pytest.mark.parametrize("body", [
    "", "<html>sem censo</html>",
    'VGPC.pop_data = {"psa":[1,2,3]};',                          # tamanho errado
    'VGPC.pop_data = {"psa":[0,0,0,0,0,0,0,0,0,1]};',            # falta a CGC
    'VGPC.pop_data = {"cgc":[0,0,0,0,0,0,0,0,0,-1],"psa":[0,0,0,0,0,0,0,0,0,1]};',
    "VGPC.pop_data = {quebrado};",
])
def test_pop_report_never_invents_zeros(body):
    assert pc.parse_pop_report(body) is None


def test_psa10_sales_per_month_reads_the_sixth_volume_cell():
    # página real: "1 sale per week" na coluna da PSA 10 → 4,3 vendas/mês
    assert pc.parse_psa10_sales_per_month(PAGE_REVERSE) == 4.3
    assert pc.parse_psa10_sales_per_month("<html>sem tabela</html>") is None


# --- página da variante exata ------------------------------------------------------

def test_variant_path_picks_the_exact_print_variant():
    paths = pc.search_card_paths(SEARCH)
    assert pc.choose_variant_path(paths, "Charmander", "9/108", SET) == \
        "/game/pokemon-evolutions/charmander-9"
    assert pc.choose_variant_path(paths, "Charmander", "9/108", SET, REVERSE) == \
        "/game/pokemon-evolutions/charmander-reverse-holo-9"


def test_variant_path_refuses_unknown_or_missing_variants():
    paths = pc.search_card_paths(SEARCH)
    # variante sem página própria reconhecida → None (nunca a página da carta comum)
    assert pc.choose_variant_path(paths, "Charmander", "9/108", SET, frozenset({"staff"})) is None
    assert pc.choose_variant_path(paths, "Charmander", "9/108", SET, frozenset({"1st"})) is None
    # "promo" é neutro (o set de promos já é o console)
    assert pc.choose_variant_path(paths, "Charmander", "9/108", SET, frozenset({"promo"})) == \
        "/game/pokemon-evolutions/charmander-9"
    # sem a página reverse nos resultados, a reverse não cai na comum
    only_base = [p for p in paths if "reverse" not in p]
    assert pc.choose_variant_path(only_base, "Charmander", "9/108", SET, REVERSE) is None


def test_grading_snapshot_reads_refs_census_and_volume(monkeypatch, frozen_today):
    _stub_fetch(monkeypatch)
    snap = pc.grading_snapshot("Charmander", "9/108", SET, (PSA.top, PSA.second), variants=REVERSE)
    assert snap.url.endswith("/charmander-reverse-holo-9")
    top, second = snap.refs["PSA 10"], snap.refs["PSA 9"]
    assert top.price == 603.5 and top.n_sales == 21 and top.liquidity == "ok"
    assert second.price == 49.99 and second.liquidity == "ok"
    assert snap.pop["psa"][9] == 754
    assert snap.psa10_sales_per_month == 4.3
    assert snap.comps_180d["PSA 10"] == 21


def test_grading_snapshot_base_page_never_borrows_reverse_sales(monkeypatch, frozen_today):
    _stub_fetch(monkeypatch)
    snap = pc.grading_snapshot("Charmander", "9/108", SET, (PSA.top, PSA.second))
    assert snap.url.endswith("/charmander-9")
    assert snap.refs["PSA 10"].price == 116.5      # carta comum: outro preço, outro censo
    assert snap.pop["psa"][9] == 985


def test_grading_snapshot_none_without_variant_page(monkeypatch):
    _stub_fetch(monkeypatch)
    assert pc.grading_snapshot("Charmander", "9/108", SET, (PSA.top,),
                               variants=frozenset({"staff"})) is None


def test_grading_snapshot_page_without_tables_is_a_source_error(monkeypatch):
    monkeypatch.setattr(pc, "fetch_page",
                        lambda url, cache_dir=None: SEARCH if "search-products" in url
                        else "<html>" + "x" * 3000 + "</html>")
    with pytest.raises(pc.PcError):
        pc.grading_snapshot("Charmander", "9/108", SET, (PSA.top,))


# --- a conta -----------------------------------------------------------------------

def _ref(price, n=5, liquidity="ok", what="PSA 10"):
    return SalesRef(price=price, n_sales=n, window_days=180 if liquidity == "ok" else 365,
                    liquidity=liquidity, url="https://www.pricecharting.com/game/x/y",
                    label=f"vendas {what} (n={n}, 2026-06..2026-11)")


def _snap(top=600.0, second=50.0, psa=None, cgc=None, per_month=4.3, top_n=21,
          top_liq="ok", second_liq="ok", comps=None):
    psa = psa if psa is not None else [1, 0, 2, 4, 20, 56, 243, 1257, 2837, 754]
    pop = None if psa == "none" else {"psa": psa, "cgc": cgc or [0, 0, 0, 2, 8, 15, 61, 614, 513, 70]}
    refs = {"PSA 10": _ref(top, top_n, top_liq) if top is not None else None,
            "PSA 9": _ref(second, 24, second_liq, "PSA 9") if second is not None else None,
            "CGC 10 GEM": _ref(top, top_n, top_liq, "CGC 10 Gem Mint") if top is not None else None,
            "CGC 9.5": _ref(second, 24, second_liq, "CGC 9.5") if second is not None else None}
    return GradingSnapshot(url="https://www.pricecharting.com/game/x/y", refs=refs, pop=pop,
                           psa10_sales_per_month=per_month, comps_180d=comps or {})


def test_case_numbers_follow_the_documented_formulas():
    c = gm.build_case(PSA, _snap(), comc_price=3.88, raw_value=3.0, grading_cost=59.0,
                      pokemon_rank=8, copies=16)
    assert c.total_cost == pytest.approx(62.88)
    assert c.spread_top == pytest.approx(600.0 - 62.88)
    assert c.spread_second == pytest.approx(50.0 - 62.88)
    assert c.breakeven_pct == pytest.approx((62.88 - 3.0) / (600.0 - 3.0) * 100)
    g10, g9 = 754 / 5174, 2837 / 5174
    assert c.gem_rate_pct == pytest.approx(g10 * 100)
    expected = g10 * 600.0 + g9 * 50.0 + (1 - g10 - g9) * 3.0 - 62.88
    assert c.ev == pytest.approx(expected)
    assert c.ev_roi_pct == pytest.approx(expected / 62.88 * 100)
    assert (c.pop_top, c.pop_second, c.pop_total, c.copies) == (754, 2837, 5174, 16)
    assert c.sales_per_month == 4.3 and c.sales_source == "pc-volume"
    # Pokémon top-10 = 25 · pop 754 = 18 · 4,3 vendas/mês = 8 · VE ≥ 50% do custo = 20
    assert (c.pts_pokemon, c.pts_scarcity, c.pts_demand, c.pts_economy) == (25, 18, 8, 20)
    assert c.score == 71


def test_case_is_none_without_a_top_grade_reference():
    assert gm.build_case(PSA, _snap(top=None), 5.0, 3.0, 59.0) is None


def test_second_grade_without_three_sales_enters_ev_at_raw_value():
    thin = gm.build_case(PSA, _snap(second_liq="thin"), 3.88, 3.0, 59.0)
    none = gm.build_case(PSA, _snap(second=None), 3.88, 3.0, 59.0)
    g10, g9 = 754 / 5174, 2837 / 5174
    conservative = g10 * 600.0 + (1 - g10) * 3.0 - 62.88
    assert thin.ev == pytest.approx(conservative) and none.ev == pytest.approx(conservative)
    assert not thin.second_usable and thin.second_price == 50.0   # preço mostrado, não usado
    assert none.second_price is None and none.spread_second is None
    assert g9 > 0  # a 2ª nota existe no censo; só não tem referência de preço


@pytest.mark.parametrize("psa, per_month, expected", [
    ("none", 4.3, "censo n/d"),
    ([0, 0, 0, 0, 0, 0, 0, 2, 10, 3], 1.0, "censo fino (total 15)"),
    ([0, 0, 0, 0, 0, 0, 5, 20, 30, 0], 1.0, "nenhuma nota máxima no censo (55 graduadas)"),
    ([0, 0, 0, 0, 0, 0, 5, 20, 30, 2], 4.3, "censo não confiável (4.3 vendas/mês com só 2 no censo)"),
])
def test_untrusted_census_gives_no_rate_and_no_ev(psa, per_month, expected):
    c = gm.build_case(PSA, _snap(psa=psa, per_month=per_month), 3.88, 3.0, 59.0)
    assert c.pop_issue == expected
    assert c.gem_rate_pct is None and c.ev is None and c.ev_roi_pct is None
    assert c.pts_scarcity == 0 and c.pts_economy == 0
    assert c.spread_top > 0 and c.breakeven_pct is not None   # a parte factual continua


def test_demand_falls_back_to_the_180_day_sample_outside_psa10():
    c = gm.build_case(CGC, _snap(per_month=30.0, comps={"CGC 10 GEM": 12}), 3.88, 3.0, 10.0)
    assert c.sales_per_month == 2.0 and c.sales_source == "amostra-180d"
    assert c.census_note == "censo-CGC-aproximado" and c.grading_cost == 10.0
    assert c.pop_top == 70 and c.pop_total == sum([0, 0, 0, 2, 8, 15, 61, 614, 513, 70])


def test_points_bands():
    assert [gm.pokemon_points(r) for r in (1, 10, 11, 25, 50, 100, 101, 9999, None)] == \
        [25, 25, 20, 20, 14, 8, 3, 3, 3]
    assert [gm.scarcity_points(p) for p in (50, 51, 500, 2000, 5000, 10000, 10001)] == \
        [25, 22, 22, 18, 12, 7, 3]
    assert [gm.demand_points(s) for s in (60, 30, 5, 2, 1.9)] == [25, 20, 14, 8, 3]
    assert [gm.economy_points(r) for r in (100, 50, 25, 0, -0.1)] == [25, 20, 14, 8, 0]


def test_plan_and_cost_helpers():
    assert gm.effective_cost(PSA, 0.0) == 59.0 and gm.effective_cost(CGC, None) == 10.0
    assert gm.effective_cost(PSA, 25.0) == 25.0
    assert gm.plan_for("cgc") is CGC
    with pytest.raises(ValueError):
        gm.plan_for("BGS")


# --- status ------------------------------------------------------------------------

def _row(case=None, **over):
    case = case or gm.build_case(PSA, _snap(), 3.88, 3.0, 59.0, pokemon_rank=8, copies=16)
    row = {"confidence": 0.95, "price_field": "market", "pokemon": "Charmander",
           "pokemon_rank": 8, "card_number": "Charmander 9/108", "set": "XY - Evolutions",
           "listing_type": "Raw NM", "sub_type": "Reverse Holofoil", "comc_price": 3.88,
           "comc_url": "https://www.comc.com/Cards/Pokemon/x/1",
           "ref_url": "https://www.pricecharting.com/game/x/y", **case.as_row()}
    row.update(over)
    return row


def test_clean_row_is_ok():
    assert gm.classify_grading_row(_row()) == ("OK", [])


@pytest.mark.parametrize("over, reason", [
    ({"confidence": 0.85}, "confiança<0.90"),
    ({"price_field": "mid"}, "cru:mid"),
    ({"grading_top_n_sales": 2}, "vendas<3(n=2)"),
    ({"grading_pop_issue": "censo n/d"}, "censo: censo n/d"),
    ({"grading_census_note": "censo-CGC-aproximado"}, "censo-CGC-aproximado"),
    ({"grading_ev": -4.2}, "VE<0"),
    ({"grading_ev_roi_pct": 300.0}, "retorno-extremo(≥300%)"),
])
def test_review_reasons(over, reason):
    status, reasons = gm.classify_grading_row(_row(**over))
    assert status == "MATCH_REVIEW" and reason in reasons


def test_extreme_return_threshold_is_inclusive_and_never_drops():
    assert gm.classify_grading_row(_row(grading_ev_roi_pct=299.9))[0] == "OK"
    assert gm.classify_grading_row(_row(grading_ev_roi_pct=425.92))[0] == "MATCH_REVIEW"


def test_notes_do_not_change_status():
    row = _row(grading_top_liquidity="low", grading_second_usable=False)
    assert gm.classify_grading_row(row)[0] == "OK"
    assert gm.grading_row_notes(row) == ["baixa-liquidez(365d)", "2ª-nota-sem-ref"]


def test_cgc_route_always_goes_to_review():
    case = gm.build_case(CGC, _snap(comps={"CGC 10 GEM": 12}), 3.88, 3.0, 10.0)
    status, reasons = gm.classify_grading_row(_row(case))
    assert status == "MATCH_REVIEW" and "censo-CGC-aproximado" in reasons


def test_sort_points_then_expected_return():
    rows = [_row(grading_score=40, grading_ev_roi_pct=300.0, card_number="A"),
            _row(grading_score=70, grading_ev_roi_pct=10.0, card_number="B"),
            _row(grading_score=70, grading_ev_roi_pct=80.0, card_number="C"),
            _row(grading_score=70, grading_ev_roi_pct=None, card_number="D")]
    assert [r["card_number"] for r in sort_rows(rows)] == ["C", "B", "D", "A"]


# --- funil do pipeline ---------------------------------------------------------------

SV_SET = "XY - Evolutions"
CTX = normalize_set(SV_SET)


def _settings(**over):
    s = load_settings(env_file=Path("/nonexistent.env"))
    _apply_overrides(s, build_parser().parse_args(["scan", "--grading"]))
    for k, v in over.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def index():
    idx = TcgIndex()
    products = [{"productId": 1, "groupId": 99, "name": "Charmander", "cleanName": "Charmander",
                 "url": "https://www.tcgplayer.com/product/1",
                 "extendedData": [{"name": "Number", "value": "9/108"},
                                  {"name": "Rarity", "value": "Common"}]}]
    prices = [{"productId": 1, "subTypeName": "Reverse Holofoil", "marketPrice": 3.0,
               "midPrice": None, "lowPrice": None, "highPrice": None, "directLowPrice": None},
              {"productId": 1, "subTypeName": "Normal", "marketPrice": 1.2,
               "midPrice": None, "lowPrice": None, "highPrice": None, "directLowPrice": None}]
    idx.add_group(99, SV_SET, "EVO", products, prices)
    return idx


def _listing(price=3.88, cond="NM", qty=16):
    return ComcListing(raw_name="Charmander", price=price,
                       url=f"https://www.comc.com/Cards/Pokemon/2016/x/9/Charmander/{price}",
                       set_hint="Pokemon XY Evolutions - 20th Anniversary Base - Reverse Foil",
                       number_hint="9", condition=cond, item_id=f"c{price}", quantity=qty)


def test_pipeline_grading_candidate_without_price_floor(monkeypatch, index):
    seen = {}

    def fake_snapshot(name, number, set_label, grades, cache_dir=None, variants=frozenset()):
        seen.update(name=name, grades=[g.key for g in grades], variants=variants)
        return _snap()

    monkeypatch.setattr(pl, "grading_snapshot", fake_snapshot)
    sc = pl.Scanner(_settings())
    deal = sc.process_listing(_listing(), index, CTX, pl.KIND_RAW)
    assert deal is not None and deal.status == "OK"          # US$3,88: abaixo do piso antigo
    assert seen["grades"] == ["PSA 10", "PSA 9"] and seen["variants"] == REVERSE
    row = deal.as_row()
    assert row["mode"] == "grading" and row["grading_total_cost"] == 62.88
    assert row["grading_copies"] == 16 and row["grading_raw_value"] == 3.0
    assert row["ref_url"] == "https://www.pricecharting.com/game/x/y"
    assert sc.stats["ok"] == 1 and sc.stats["below_discount"] == 0


@pytest.mark.parametrize("snapshot, counter", [
    (None, "grading_no_page"),
    (_snap(top=None), "grading_no_top_reference"),
    (_snap(top=40.0), "grading_top_below_cost"),     # US$40 < US$62,88 de custo
])
def test_pipeline_grading_exits_are_counted(monkeypatch, index, snapshot, counter):
    monkeypatch.setattr(pl, "grading_snapshot", lambda *a, **k: snapshot)
    sc = pl.Scanner(_settings())
    assert sc.process_listing(_listing(), index, CTX, pl.KIND_RAW) is None
    assert sc.stats[counter] == 1


def test_pipeline_grading_source_error_is_not_a_missing_reference(monkeypatch, index):
    def boom(*a, **k):
        raise pc.PcError("bloqueio")
    monkeypatch.setattr(pl, "grading_snapshot", boom)
    sc = pl.Scanner(_settings())
    assert sc.process_listing(_listing(), index, CTX, pl.KIND_RAW) is None
    assert sc.stats["grading_pc_error"] == 1 and sc.stats["grading_no_page"] == 0


def test_pipeline_grading_respects_ceiling_and_nm_only(monkeypatch, index):
    monkeypatch.setattr(pl, "grading_snapshot", lambda *a, **k: _snap())
    sc = pl.Scanner(_settings())
    assert sc.process_listing(_listing(price=100.01), index, CTX, pl.KIND_RAW) is None
    assert sc.stats["skip_price_ceiling"] == 1
    assert sc.process_listing(_listing(cond="LP"), index, CTX, pl.KIND_RAW) is None
    assert sc.process_listing(_listing(cond="EX-NM"), index, CTX, pl.KIND_RAW) is None
    assert sc.stats["skip_condition"] == 2


def test_arbitrage_scan_is_untouched_by_default(monkeypatch, index):
    def never(*a, **k):
        raise AssertionError("o scan normal não pode consultar o modo grading")
    monkeypatch.setattr(pl, "grading_snapshot", never)
    s = load_settings(env_file=Path("/nonexistent.env"))
    s.min_comc_price = 0.0
    sc = pl.Scanner(s)
    deal = sc.process_listing(_listing(price=2.0), index, CTX, pl.KIND_RAW)
    assert deal is not None and deal.grading is None and "mode" not in deal.as_row()


# --- CLI -----------------------------------------------------------------------------

def test_cli_grading_defaults_follow_the_operator_rule():
    s = _settings()
    assert s.grading_mode and s.grading_grader == "PSA" and s.grading_cost_usd == 59.0
    assert s.scan_raw and not s.scan_slabs and s.raw_conditions == frozenset({"nm"})
    assert s.min_comc_price == 0.0 and s.max_comc_price == GRADING_DEFAULT_MAX_PRICE == 100.0


def test_cli_grading_explicit_flags_win():
    s = load_settings(env_file=Path("/nonexistent.env"))
    _apply_overrides(s, build_parser().parse_args(
        ["scan", "--grading", "--grader", "cgc", "--grading-cost", "12.5",
         "--min-price", "2", "--max-price", "40"]))
    assert (s.grading_grader, s.grading_cost_usd) == ("CGC", 12.5)
    assert (s.min_comc_price, s.max_comc_price) == (2.0, 40.0)


def test_cli_without_grading_keeps_the_fleet_floor():
    s = load_settings(env_file=Path("/nonexistent.env"))
    _apply_overrides(s, build_parser().parse_args(["scan", "--grader", "CGC"]))
    assert not s.grading_mode and s.min_comc_price == 10.0 and s.scan_slabs


@pytest.mark.parametrize("argv", [
    ["scan", "--grading", "--grader", "BGS"],
    ["scan", "--grading", "--grading-cost", "0"],
    ["scan", "--grading", "--slabs-only"],
])
def test_cli_grading_rejects_bad_input(argv):
    with pytest.raises(SystemExit):
        main(argv)


def test_cli_invalid_grader_in_env_is_an_explicit_error(monkeypatch):
    s = load_settings(env_file=Path("/nonexistent.env"))
    s.grading_grader = "BGS"
    with pytest.raises(ValueError):
        _apply_overrides(s, build_parser().parse_args(["scan", "--grading"]))


# --- entrega -------------------------------------------------------------------------

def _payload(rows, **over):
    payload = {"scope": "grading_grupo9", "generated_utc": "20261116T220000Z", "mode": "grading",
               "grading_grader": "PSA", "grading_cost_usd": 59.0, "max_comc_price": 100.0,
               "min_comc_price": 0.0, "languages": ["en"], "iconic_only": False,
               "trust_confidence": 0.90, "top_n": 0, "count": len(rows),
               "funnel": {"seen": 300, "grading_top_below_cost": 120, "ok": 1, "review": 1},
               "deals": rows, "low_confidence": []}
    payload.update(over)
    return payload


def test_summary_grading_delivery_has_two_buckets_and_the_assumptions():
    rows = [_row(card_number="Charmander 9/108"),
            _row(card_number="Machoke 58/108", grading_ev=-3.0, grading_ev_roi_pct=-4.8)]
    md = comc_summary.build_markdown(_payload(rows), group=9)
    ok_part, review_part = md.split(comc_summary.GRADING_REVIEW_TITLE)
    assert comc_summary.GRADING_OK_TITLE in ok_part
    assert "Charmander 9/108" in ok_part and "Machoke 58/108" in review_part
    assert "VE<0" in review_part
    assert "Rota: PSA 10 (2ª nota: PSA 9) · custo de graduar: US$59.0" in md
    assert "teto COMC: US$100.0 · piso: US$sem piso" in md
    assert "Grading: nem a nota máxima paga o custo total (COMC + graduar): 120" in md
    assert "não é recomendação de compra" in md and "HISTÓRICA" in md
    assert "Desconto mínimo" not in md          # cabeçalho da arbitragem não vaza


def test_grading_table_shows_nd_never_a_made_up_zero():
    case = gm.build_case(PSA, _snap(psa="none", second=None), 3.88, 3.0, 59.0)
    line = render_grading_table([_row(case)]).splitlines()[2]
    cells = [c.strip() for c in line.strip("|").split("|")]
    header = [c.strip() for c in render_grading_table([]).splitlines()[0].strip("|").split("|")]
    by = dict(zip(header, cells))
    assert by["Retorno esperado%"] == "n/d" and by["Taxa nota máx%"] == "n/d"
    assert by["Pop nota máx/total"] == "n/d" and by["2ª nota$"] == "n/d (PSA 9)"
    assert by["Nota máx$"] == "600.00 (PSA 10)" and by["Custo$"] == "62.88"
    assert by["Tipo"] == "Raw NM · Reverse Holofoil"
    assert "censo: censo n/d" in by["Status"]
    assert "[oferta](https://www.comc.com/Cards/Pokemon/x/1)" in by["Links"]


def test_grading_sample_marks_demand_as_a_floor():
    case = gm.build_case(CGC, _snap(comps={"CGC 10 GEM": 12}), 3.88, 3.0, 10.0)
    line = render_grading_table([_row(case)]).splitlines()[2]
    assert "| ≥2 |" in line


def test_summary_cli_writes_the_grading_markdown(tmp_path, capsys):
    src, out = tmp_path / "in.json", tmp_path / "out.md"
    src.write_text(json.dumps(_payload([_row()])), encoding="utf-8")
    assert comc_summary.main([str(src), "-o", str(out), "--group", "9"]) == 0
    assert "COMC → graduar" in out.read_text(encoding="utf-8")


# --- marcador de era com hífen ("XY - …", "SM - …") -------------------------------------

@pytest.mark.parametrize("set_label, console", [
    ("XY - Evolutions", "pokemon-evolutions"),
    ("XY - BREAKthrough", "pokemon-breakthrough"),
    ("SM - Team Up", "pokemon-team-up"),
    ("SWSH07: Evolving Skies", "pokemon-evolving-skies"),
])
def test_console_matches_sets_with_era_marker(set_label, console):
    assert pc.console_matches(f"/game/{console}/charmander-9", set_label)


def test_era_marker_never_loosens_the_set_guard():
    # tiragem japonesa e set parecido continuam fora (guarda bidirecional)
    assert not pc.console_matches("/game/pokemon-japanese-evolutions/charmander-9", "XY - Evolutions")
    assert not pc.console_matches("/game/pokemon-evolutions/charmander-9", "XY - Steam Siege")
    assert pc.clean_set_name("XY Base Set") == "XY Base Set"      # sem hífen: intocado
