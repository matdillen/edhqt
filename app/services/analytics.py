from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import re
from urllib.parse import quote


COLOR_ORDER = ("W", "U", "B", "R", "G", "C")
TYPE_ORDER = ("Land", "Creature", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker", "Battle")
STAPLES_FILE = Path("data/staples.txt")

STAT_META = {
    "Power": {
        "class_name": "stat-power",
        "description": "Blends efficiency, consistency, tutors, wipes, staples, game changers, and salt into a 0-10 ceiling estimate.",
        "implication": "Higher scores usually mean a stronger, faster, and more punishing table presence.",
    },
    "Efficiency": {
        "class_name": "stat-efficiency",
        "description": "Weighted from average mana value, ramp, draw, cheap interaction, and nonland spell density.",
        "implication": "Higher scores suggest the deck spends mana well and gets online earlier.",
    },
    "Consistency": {
        "class_name": "stat-consistency",
        "description": "Combines land ratio, color production versus color demand, ramp, and card draw.",
        "implication": "Higher scores mean fewer awkward draws and smoother mana over a long game.",
    },
    "Avg MV": {
        "class_name": "stat-curve",
        "description": "Average mana value of nonland cards only.",
        "implication": "Lower values usually mean a faster curve; higher values point to a slower, heavier plan.",
    },
    "Lands": {
        "class_name": "stat-mana",
        "description": "Counts lands in the list and shows them against total cards.",
        "implication": "Too low can lead to missed land drops; too high can reduce spell density.",
    },
    "Salt": {
        "class_name": "stat-salt",
        "description": "Average EDHREC saltiness from the local card data across the full deck.",
        "implication": "Higher values usually indicate cards opponents may find more frustrating or swingy.",
    },
    "Ramp": {
        "class_name": "stat-support",
        "description": "Cards detected as mana acceleration through land search, mana abilities, or Treasure creation.",
        "implication": "More ramp generally means faster development and easier access to expensive plays.",
    },
    "Draw": {
        "class_name": "stat-support",
        "description": "Cards whose rules text explicitly draws cards.",
        "implication": "Higher draw counts help the deck keep gas and recover from attrition.",
    },
    "Tutors": {
        "class_name": "stat-power",
        "description": "Cards that search your library for nonland targets.",
        "implication": "More tutors raise deck precision and power, but can make games play more similarly.",
    },
    "Removal": {
        "class_name": "stat-interaction",
        "description": "Spot interaction detected from target-based destroy, exile, bounce, fight, sacrifice, or damage text.",
        "implication": "Higher counts give the deck more answers to single threats.",
    },
    "Wipes": {
        "class_name": "stat-interaction",
        "description": "Mass removal patterns such as 'destroy all', 'exile all', or similar sweep effects.",
        "implication": "More wipes improve reset potential but can slow the game and strain your own board plan.",
    },
    "Counters": {
        "class_name": "stat-interaction",
        "description": "Cards with counterspell-style text such as 'counter target' or 'counter up to'.",
        "implication": "Higher counts improve stack interaction and protection against explosive turns.",
    },
    "Recursion": {
        "class_name": "stat-recursion",
        "description": "Cards that return cards from your graveyard to hand or battlefield.",
        "implication": "More recursion increases resilience after removal or self-mill.",
    },
    "Staples": {
        "class_name": "stat-power",
        "description": "Cards present in the local staples list at data/staples.txt.",
        "implication": "Higher staple density often correlates with stronger generic card quality.",
    },
    "Game Changers": {
        "class_name": "stat-salt",
        "description": "Cards flagged in the local metadata as game changers.",
        "implication": "More game changers usually means higher swing potential and a stronger ceiling.",
    },
    "Decks": {
        "class_name": "stat-neutral",
        "description": "The number of decks included in the current summary.",
        "implication": "Useful for judging whether collection averages reflect a broad sample or just a few lists.",
    },
    "Avg Power": {
        "class_name": "stat-power",
        "description": "Average of each deck's computed power score.",
        "implication": "Higher values mean your overall collection trends stronger.",
    },
    "Avg Efficiency": {
        "class_name": "stat-efficiency",
        "description": "Average of each deck's efficiency score.",
        "implication": "Higher values suggest your collection skews toward leaner, faster decks.",
    },
    "Avg Consistency": {
        "class_name": "stat-consistency",
        "description": "Average of each deck's consistency score.",
        "implication": "Higher values suggest your decks tend to mulligan and curve out more reliably.",
    },
    "Avg Lands": {
        "class_name": "stat-mana",
        "description": "Average land count across the selected decks.",
        "implication": "Helps spot whether your collection as a whole is running lean or mana-heavy.",
    },
}

TABLE_HEADER_META = {
    "Deck": "Deck name used for this comparison row.",
    "Power": "Overall 0-10 score that blends speed, consistency, and ceiling.",
    "Efficiency": "How lean and mana-efficient the deck looks from curve, ramp, draw, and interaction.",
    "Consistency": "How reliably the deck should hit lands, colors, and velocity pieces.",
    "Avg MV": "Average mana value of nonland cards in the deck.",
    "Lands": "Total lands in the list.",
    "Ramp": "Cards tagged as mana acceleration.",
    "Draw": "Cards tagged as card draw.",
    "Interaction": "Spot removal plus counterspells.",
    "GC": "Cards flagged as game changers in the local metadata.",
}


def get_stat_help_text(label: str) -> Optional[str]:
    meta = STAT_META.get(label)
    if not meta:
        return None
    return f"{label}\n\nCalculated as: {meta['description']}\n\nWhat it implies: {meta['implication']}"


@dataclass
class DeckStats:
    deck_name: str
    total_cards: int
    nonland_count: int
    land_count: int
    avg_mana_value: float
    power_score: float
    efficiency_score: float
    consistency_score: float
    avg_saltiness: float
    staples_count: int
    game_changers: int
    ramp: int
    card_draw: int
    tutors: int
    spot_removal: int
    board_wipes: int
    counterspells: int
    recursion: int
    mana_curve: Dict[int, int]
    type_counts: Dict[str, int]
    color_demand: Dict[str, int]
    color_production: Dict[str, int]


def cmc_from_value(mana_value: Optional[str]) -> Optional[int]:
    if mana_value is None or mana_value == "":
        return None
    try:
        return int(float(mana_value))
    except Exception:
        return None


def compute_deck_stats(
    deck_name: str,
    deck_cards: List[Tuple[str, int]],
    get_card_meta: Callable[[str], dict],
) -> DeckStats:
    staples = _load_staples()
    total_cards = sum(qty for _, qty in deck_cards)
    land_count = 0
    nonland_count = 0
    mana_curve: Counter[int] = Counter()
    type_counts: Counter[str] = Counter()
    color_demand: Counter[str] = Counter()
    color_production: Counter[str] = Counter()
    mana_value_total = 0.0
    mana_value_cards = 0
    game_changers = 0
    staples_count = 0
    ramp = 0
    card_draw = 0
    tutors = 0
    spot_removal = 0
    board_wipes = 0
    counterspells = 0
    recursion = 0
    saltiness_total = 0.0

    for card_name, qty in deck_cards:
        meta = get_card_meta(card_name) or {}
        type_line = meta.get("type") or ""
        text = (meta.get("text") or "").lower()
        mana_cost = meta.get("manaCost") or ""
        produced_mana = meta.get("producedMana") or ""
        is_land = "land" in type_line.lower()

        for type_name in TYPE_ORDER:
            if type_name.lower() in type_line.lower():
                type_counts[type_name] += qty

        if is_land:
            land_count += qty
        else:
            nonland_count += qty

        mv = _float_or_none(meta.get("manaValue"))
        if mv is not None and not is_land:
            mana_value_total += mv * qty
            mana_value_cards += qty
            mana_curve[int(mv)] += qty

        for color, amount in _count_mana_symbols(mana_cost).items():
            color_demand[color] += amount * qty
        for color, amount in _count_produced_mana(produced_mana, text).items():
            color_production[color] += amount * qty

        if _is_game_changer(meta):
            game_changers += qty
        if card_name.lower() in staples:
            staples_count += qty

        if _is_ramp(type_line, text):
            ramp += qty
        if _is_card_draw(text):
            card_draw += qty
        if _is_tutor(text):
            tutors += qty
        if _is_spot_removal(text):
            spot_removal += qty
        if _is_board_wipe(text):
            board_wipes += qty
        if _is_counterspell(text):
            counterspells += qty
        if _is_recursion(text):
            recursion += qty

        saltiness_total += max(_float_or_zero(meta.get("edhrecSaltiness")), 0.0) * qty

    avg_mana_value = mana_value_total / mana_value_cards if mana_value_cards else 0.0
    avg_saltiness = saltiness_total / max(total_cards, 1)

    efficiency_score = _compute_efficiency_score(avg_mana_value, ramp, card_draw, spot_removal, counterspells, nonland_count)
    consistency_score = _compute_consistency_score(land_count, total_cards, color_demand, color_production, ramp, card_draw)
    power_score = _compute_power_score(
        efficiency_score=efficiency_score,
        consistency_score=consistency_score,
        tutors=tutors,
        board_wipes=board_wipes,
        staples_count=staples_count,
        game_changers=game_changers,
        avg_saltiness=avg_saltiness,
    )

    return DeckStats(
        deck_name=deck_name,
        total_cards=total_cards,
        nonland_count=nonland_count,
        land_count=land_count,
        avg_mana_value=avg_mana_value,
        power_score=power_score,
        efficiency_score=efficiency_score,
        consistency_score=consistency_score,
        avg_saltiness=avg_saltiness,
        staples_count=staples_count,
        game_changers=game_changers,
        ramp=ramp,
        card_draw=card_draw,
        tutors=tutors,
        spot_removal=spot_removal,
        board_wipes=board_wipes,
        counterspells=counterspells,
        recursion=recursion,
        mana_curve=dict(sorted(mana_curve.items())),
        type_counts={key: type_counts.get(key, 0) for key in TYPE_ORDER if type_counts.get(key, 0)},
        color_demand={key: color_demand.get(key, 0) for key in COLOR_ORDER if color_demand.get(key, 0)},
        color_production={key: color_production.get(key, 0) for key in COLOR_ORDER if color_production.get(key, 0)},
    )


def build_deck_stats_html(stats: DeckStats) -> str:
    headline = _summary_cards_html([
        ("Power", f"{stats.power_score:.1f} / 10"),
        ("Efficiency", f"{stats.efficiency_score:.1f} / 10"),
        ("Consistency", f"{stats.consistency_score:.1f} / 10"),
        ("Avg MV", f"{stats.avg_mana_value:.2f}"),
        ("Lands", f"{stats.land_count} / {stats.total_cards}"),
        ("Salt", f"{stats.avg_saltiness:.2f}"),
    ])
    role_cards = _summary_cards_html([
        ("Ramp", str(stats.ramp)),
        ("Draw", str(stats.card_draw)),
        ("Tutors", str(stats.tutors)),
        ("Removal", str(stats.spot_removal)),
        ("Wipes", str(stats.board_wipes)),
        ("Counters", str(stats.counterspells)),
        ("Recursion", str(stats.recursion)),
        ("Staples", str(stats.staples_count)),
        ("Game Changers", str(stats.game_changers)),
    ])
    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: Segoe UI, sans-serif; color: #e7e7e7; background: #1e1e1e; }}
        h1, h2 {{ color: #ffffff; }}
        .muted {{ color: #9aa0a6; }}
        .grid {{ margin: 12px 0 18px 0; }}
        .card {{
          display: inline-block;
          min-width: 118px;
          margin: 0 10px 10px 0;
          padding: 10px 12px;
          border: 1px solid #3a3a3a;
          border-left: 4px solid #5a5a5a;
          border-radius: 10px;
          background: #252526;
          vertical-align: top;
        }}
        .card:hover {{ border-color: #666; }}
        .label {{ color: #9aa0a6; font-size: 11px; text-transform: uppercase; }}
        .value {{ color: #ffffff; font-size: 20px; font-weight: 700; margin-top: 4px; }}
        a.info {{
          display: inline-block;
          margin-left: 6px;
          padding: 0 5px;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.14);
          color: #f2f2f2;
          font-size: 11px;
          font-weight: 700;
          text-decoration: none;
        }}
        .stat-power {{ background: linear-gradient(180deg, #31241b 0%, #252526 100%); border-left-color: #d18b47; }}
        .stat-efficiency {{ background: linear-gradient(180deg, #152a22 0%, #252526 100%); border-left-color: #4db887; }}
        .stat-consistency {{ background: linear-gradient(180deg, #1f2536 0%, #252526 100%); border-left-color: #6ba6ff; }}
        .stat-curve {{ background: linear-gradient(180deg, #2d2235 0%, #252526 100%); border-left-color: #b786ff; }}
        .stat-mana {{ background: linear-gradient(180deg, #2d2a1c 0%, #252526 100%); border-left-color: #d6b74f; }}
        .stat-salt {{ background: linear-gradient(180deg, #352127 0%, #252526 100%); border-left-color: #ef6b73; }}
        .stat-support {{ background: linear-gradient(180deg, #17302b 0%, #252526 100%); border-left-color: #4fc7b5; }}
        .stat-interaction {{ background: linear-gradient(180deg, #2a1f34 0%, #252526 100%); border-left-color: #be7cff; }}
        .stat-recursion {{ background: linear-gradient(180deg, #1d3023 0%, #252526 100%); border-left-color: #78c850; }}
        .stat-neutral {{ background: linear-gradient(180deg, #2a2a2a 0%, #252526 100%); border-left-color: #8c8c8c; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
        th, td {{ border-bottom: 1px solid #333; padding: 7px 8px; text-align: left; }}
        th {{ color: #cfcfcf; background: #262626; }}
      </style>
    </head>
    <body>
      <h1>{escape(stats.deck_name)} Deck Stats</h1>
      <p class="muted">Local EDH insights modeled after EDH Power Level style metrics, using your offline card database and decklists.</p>
      <div class="grid">{headline}</div>
      <h2>Deck Roles</h2>
      <div class="grid">{role_cards}</div>
      <h2>Mana Curve</h2>
      {_key_value_table_html("Mana Value", "Cards", stats.mana_curve)}
      <h2>Type Breakdown</h2>
      {_key_value_table_html("Type", "Count", stats.type_counts)}
      <h2>Color Demand Vs Production</h2>
      {_color_table_html(stats.color_demand, stats.color_production)}
    </body>
    </html>
    """


def build_collection_stats_html(stats_list: Iterable[DeckStats]) -> str:
    stats = sorted(stats_list, key=lambda item: (-item.power_score, item.deck_name.lower()))
    total_decks = len(stats)
    if not total_decks:
        return "<html><body><h1>No deck stats available.</h1></body></html>"

    avg_power = sum(item.power_score for item in stats) / total_decks
    avg_efficiency = sum(item.efficiency_score for item in stats) / total_decks
    avg_consistency = sum(item.consistency_score for item in stats) / total_decks
    avg_mv = sum(item.avg_mana_value for item in stats) / total_decks
    avg_lands = sum(item.land_count for item in stats) / total_decks

    headline = _summary_cards_html([
        ("Decks", str(total_decks)),
        ("Avg Power", f"{avg_power:.1f} / 10"),
        ("Avg Efficiency", f"{avg_efficiency:.1f} / 10"),
        ("Avg Consistency", f"{avg_consistency:.1f} / 10"),
        ("Avg MV", f"{avg_mv:.2f}"),
        ("Avg Lands", f"{avg_lands:.1f}"),
    ])

    rows = []
    for item in stats:
        rows.append(
            "<tr>"
            f"<td>{escape(item.deck_name)}</td>"
            f"<td>{item.power_score:.1f}</td>"
            f"<td>{item.efficiency_score:.1f}</td>"
            f"<td>{item.consistency_score:.1f}</td>"
            f"<td>{item.avg_mana_value:.2f}</td>"
            f"<td>{item.land_count}</td>"
            f"<td>{item.ramp}</td>"
            f"<td>{item.card_draw}</td>"
            f"<td>{item.spot_removal + item.counterspells}</td>"
            f"<td>{item.game_changers}</td>"
            "</tr>"
        )

    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: Segoe UI, sans-serif; color: #e7e7e7; background: #1e1e1e; }}
        h1, h2 {{ color: #ffffff; }}
        .muted {{ color: #9aa0a6; }}
        .card {{
          display: inline-block;
          min-width: 118px;
          margin: 0 10px 10px 0;
          padding: 10px 12px;
          border: 1px solid #3a3a3a;
          border-left: 4px solid #5a5a5a;
          border-radius: 10px;
          background: #252526;
          vertical-align: top;
        }}
        .card:hover {{ border-color: #666; }}
        .label {{ color: #9aa0a6; font-size: 11px; text-transform: uppercase; }}
        .value {{ color: #ffffff; font-size: 20px; font-weight: 700; margin-top: 4px; }}
        a.info {{
          display: inline-block;
          margin-left: 6px;
          padding: 0 5px;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.14);
          color: #f2f2f2;
          font-size: 11px;
          font-weight: 700;
          text-decoration: none;
        }}
        .stat-power {{ background: linear-gradient(180deg, #31241b 0%, #252526 100%); border-left-color: #d18b47; }}
        .stat-efficiency {{ background: linear-gradient(180deg, #152a22 0%, #252526 100%); border-left-color: #4db887; }}
        .stat-consistency {{ background: linear-gradient(180deg, #1f2536 0%, #252526 100%); border-left-color: #6ba6ff; }}
        .stat-curve {{ background: linear-gradient(180deg, #2d2235 0%, #252526 100%); border-left-color: #b786ff; }}
        .stat-mana {{ background: linear-gradient(180deg, #2d2a1c 0%, #252526 100%); border-left-color: #d6b74f; }}
        .stat-salt {{ background: linear-gradient(180deg, #352127 0%, #252526 100%); border-left-color: #ef6b73; }}
        .stat-support {{ background: linear-gradient(180deg, #17302b 0%, #252526 100%); border-left-color: #4fc7b5; }}
        .stat-interaction {{ background: linear-gradient(180deg, #2a1f34 0%, #252526 100%); border-left-color: #be7cff; }}
        .stat-recursion {{ background: linear-gradient(180deg, #1d3023 0%, #252526 100%); border-left-color: #78c850; }}
        .stat-neutral {{ background: linear-gradient(180deg, #2a2a2a 0%, #252526 100%); border-left-color: #8c8c8c; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
        th, td {{ border-bottom: 1px solid #333; padding: 7px 8px; text-align: left; }}
        th {{ color: #cfcfcf; background: #262626; }}
      </style>
    </head>
    <body>
      <h1>All Decks Summary</h1>
      <p class="muted">Quick comparison across your local deck collection.</p>
      <div>{headline}</div>
      <h2>Deck Ranking</h2>
      <table>
        <thead>
          <tr>
            {_table_header_html("Deck")}
            {_table_header_html("Power")}
            {_table_header_html("Efficiency")}
            {_table_header_html("Consistency")}
            {_table_header_html("Avg MV")}
            {_table_header_html("Lands")}
            {_table_header_html("Ramp")}
            {_table_header_html("Draw")}
            {_table_header_html("Interaction")}
            {_table_header_html("GC")}
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </body>
    </html>
    """


def _summary_cards_html(entries: List[Tuple[str, str]]) -> str:
    return "".join(
        (
            f"<div class='card {_stat_class(label)}'>"
            f"<div class='label'>{escape(label)} {_info_badge_html(label)}</div>"
            f"<div class='value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in entries
    )


def _stat_class(label: str) -> str:
    return STAT_META.get(label, {}).get("class_name", "stat-neutral")


def _info_badge_html(label: str) -> str:
    meta = STAT_META.get(label)
    if not meta:
        return ""
    return f"<a class='info' href='stat:{quote(label)}'>?</a>"


def _table_header_html(label: str) -> str:
    tooltip = TABLE_HEADER_META.get(label)
    title = f" title='{escape(tooltip, quote=True)}'" if tooltip else ""
    return f"<th{title}>{escape(label)}</th>"


def _key_value_table_html(first_col: str, second_col: str, values: Dict[object, object]) -> str:
    rows = "".join(
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
        for key, value in values.items()
    ) or f"<tr><td colspan='2'>No data</td></tr>"
    return (
        "<table>"
        f"<thead><tr><th>{escape(first_col)}</th><th>{escape(second_col)}</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _color_table_html(demand: Dict[str, int], production: Dict[str, int]) -> str:
    rows = []
    for color in COLOR_ORDER:
        if color not in demand and color not in production:
            continue
        rows.append(
            "<tr>"
            f"<td>{color}</td>"
            f"<td>{demand.get(color, 0)}</td>"
            f"<td>{production.get(color, 0)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='3'>No colored mana data</td></tr>")
    return (
        "<table>"
        "<thead><tr><th>Color</th><th>Demand</th><th>Production</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _compute_efficiency_score(avg_mv: float, ramp: int, card_draw: int, spot_removal: int, counterspells: int, nonland_count: int) -> float:
    curve_score = _clamp(10 - max(avg_mv - 2.2, 0) * 3.0, 0, 10)
    ramp_score = _target_band_score(ramp, 8, 14)
    draw_score = _target_band_score(card_draw, 7, 14)
    cheap_interaction = spot_removal + counterspells
    interaction_score = _target_band_score(cheap_interaction, 6, 14)
    density_bonus = _clamp((nonland_count / 63.0) * 10, 0, 10)
    return round((curve_score * 0.35) + (ramp_score * 0.25) + (draw_score * 0.2) + (interaction_score * 0.15) + (density_bonus * 0.05), 2)


def _compute_consistency_score(
    land_count: int,
    total_cards: int,
    color_demand: Dict[str, int],
    color_production: Dict[str, int],
    ramp: int,
    card_draw: int,
) -> float:
    land_ratio = land_count / max(total_cards, 1)
    land_score = _clamp(10 - abs(0.37 - land_ratio) * 70, 0, 10)
    color_score = _color_balance_score(color_demand, color_production)
    ramp_score = _target_band_score(ramp, 8, 14)
    draw_score = _target_band_score(card_draw, 7, 14)
    return round((land_score * 0.35) + (color_score * 0.35) + (ramp_score * 0.15) + (draw_score * 0.15), 2)


def _compute_power_score(
    efficiency_score: float,
    consistency_score: float,
    tutors: int,
    board_wipes: int,
    staples_count: int,
    game_changers: int,
    avg_saltiness: float,
) -> float:
    ceiling = (
        _target_band_score(tutors, 1, 4) * 0.35
        + _target_band_score(board_wipes, 1, 4) * 0.2
        + _clamp(staples_count / 10.0, 0, 1) * 10 * 0.2
        + _clamp(game_changers / 4.0, 0, 1) * 10 * 0.15
        + _clamp(avg_saltiness / 1.5, 0, 1) * 10 * 0.1
    )
    return round((efficiency_score * 0.45) + (consistency_score * 0.35) + (ceiling * 0.2), 2)


def _color_balance_score(color_demand: Dict[str, int], color_production: Dict[str, int]) -> float:
    active_colors = [color for color, amount in color_demand.items() if color != "C" and amount > 0]
    if not active_colors:
        return 7.0
    ratios = []
    for color in active_colors:
        demand = color_demand.get(color, 0)
        production = color_production.get(color, 0)
        if demand <= 0:
            continue
        ratios.append(min(production / demand, 1.2))
    if not ratios:
        return 3.0
    return round(_clamp((sum(ratios) / len(ratios)) * 8.5, 0, 10), 2)


def _target_band_score(value: int, low: int, high: int) -> float:
    if low <= value <= high:
        return 10.0
    if value < low:
        return _clamp(10 - (low - value) * 1.4, 0, 10)
    return _clamp(10 - (value - high) * 0.9, 0, 10)


def _count_mana_symbols(mana_cost: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost or ""):
        parts = symbol.upper().split("/")
        colors = [part for part in parts if part in COLOR_ORDER]
        for color in colors:
            counts[color] += 1
    return counts


def _count_produced_mana(produced_mana: str, text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for piece in re.split(r",\s*", produced_mana or ""):
        symbol = piece.strip().upper()
        if symbol in COLOR_ORDER:
            counts[symbol] += 1
    if not counts:
        for symbol in re.findall(r"add\s+\{([WUBRGC])\}", text or "", flags=re.IGNORECASE):
            counts[symbol.upper()] += 1
    if "any color" in (text or ""):
        for color in COLOR_ORDER[:5]:
            counts[color] += 1
    return counts


def _is_ramp(type_line: str, text: str) -> bool:
    return (
        ("search your library" in text and "land" in text)
        or "add {" in text
        or "create a treasure" in text
        or "create treasure" in text
        or ("artifact" in type_line.lower() and "{t}: add" in text)
    )


def _is_card_draw(text: str) -> bool:
    return bool(re.search(r"draw [a-z0-9x]+ card", text))


def _is_tutor(text: str) -> bool:
    return "search your library for" in text and "basic land" not in text and "land card" not in text


def _is_spot_removal(text: str) -> bool:
    patterns = [
        "destroy target",
        "exile target",
        "return target",
        "counter target",
        "fight target",
        "deals damage to target",
        "target player sacrifices",
    ]
    return any(pattern in text for pattern in patterns)


def _is_board_wipe(text: str) -> bool:
    patterns = [
        "destroy all",
        "exile all",
        "each creature",
        "all creatures get",
        "all artifacts",
        "all enchantments",
        "each artifact",
    ]
    return any(pattern in text for pattern in patterns)


def _is_counterspell(text: str) -> bool:
    return "counter target" in text or "counter up to" in text


def _is_recursion(text: str) -> bool:
    patterns = [
        "return target creature card from your graveyard",
        "return target card from your graveyard",
        "return up to one target card from your graveyard",
        "from your graveyard to your hand",
        "from your graveyard to the battlefield",
    ]
    return any(pattern in text for pattern in patterns)


def _is_game_changer(meta: dict) -> bool:
    value = meta.get("isGameChanger")
    return str(value).strip().lower() in {"1", "true"}


def _float_or_none(value: object) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _float_or_zero(value: object) -> float:
    return _float_or_none(value) or 0.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@lru_cache(maxsize=1)
def _load_staples() -> set[str]:
    if not STAPLES_FILE.exists():
        return set()
    return {
        line.strip().lower()
        for line in STAPLES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
