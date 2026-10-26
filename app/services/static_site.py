from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from html import escape
from pathlib import Path
from shutil import copy2
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import json
import re
from urllib.parse import quote

from app.services.analytics import DeckStats, TYPE_ORDER, compute_deck_stats
from app.services.decks import read_mainboard, sanitize_name
from app.services.images import safe_stem


COLOR_ORDER = ("W", "U", "B", "R", "G")
SECTION_ORDER = ("Commander", "Creature", "Artifact", "Enchantment", "Planeswalker", "Battle", "Instant", "Sorcery", "Land", "Other")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "deck"


def read_commanders(file_path: str) -> List[str]:
    import xml.etree.ElementTree as ET

    root = ET.parse(file_path).getroot()
    return sanitize_name([card.attrib["name"] for card in root.findall("./zone[@name='side']/card")])


def build_static_deck(
    deck_name: str,
    file_path: str,
    color_identity: str,
    get_card_meta: Callable[[str], dict],
    image_lookup: Dict[str, str],
    image_output_dir: Path,
) -> dict:
    commanders = read_commanders(file_path)
    mainboard = read_mainboard(file_path)
    all_cards = [(name, qty) for name, qty in mainboard]
    for commander in commanders:
        if not any(name == commander for name, _qty in all_cards):
            all_cards.insert(0, (commander, 1))

    stats = compute_deck_stats(deck_name, mainboard, get_card_meta)
    card_rows = [
        _build_card_row(name, qty, name in commanders, get_card_meta(name), image_lookup, image_output_dir)
        for name, qty in all_cards
    ]

    return {
        "name": deck_name,
        "slug": slugify(deck_name),
        "file_path": file_path,
        "color_identity": color_identity or "",
        "commanders": commanders,
        "stats": stats,
        "stats_dict": asdict(stats),
        "cards": card_rows,
        "sections": _section_cards(card_rows),
        "commander_images": [card["image"] for card in card_rows if card["is_commander"] and card["image"]],
    }


def build_site_data(
    deck_files: Dict[str, str],
    color_ids: Dict[str, str],
    get_card_meta: Callable[[str], dict],
    image_lookup: Dict[str, str],
    image_output_dir: Path,
) -> List[dict]:
    used_slugs = set()
    decks = []
    for deck_name, file_path in sorted(deck_files.items(), key=lambda item: item[0].lower()):
        deck = build_static_deck(deck_name, file_path, color_ids.get(deck_name, ""), get_card_meta, image_lookup, image_output_dir)
        base_slug = deck["slug"]
        suffix = 2
        while deck["slug"] in used_slugs:
            deck["slug"] = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(deck["slug"])
        decks.append(deck)
    return decks


def render_index_html(decks: Iterable[dict]) -> str:
    deck_list = list(decks)
    summary = _collection_summary(deck_list)
    deck_cards = "\n".join(_render_deck_card(deck) for deck in deck_list)
    data = _json_for_script([
        {
            "name": deck["name"],
            "slug": deck["slug"],
            "colors": deck["color_identity"],
            "power": deck["stats"].power_score,
            "avgMv": deck["stats"].avg_mana_value,
            "lands": deck["stats"].land_count,
        }
        for deck in deck_list
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EDH Decks</title>
  <link rel="stylesheet" href="assets/site.css">
</head>
<body>
  <header class="site-header">
    <div>
      <p class="eyebrow">Local Commander Collection</p>
      <h1>EDH Decks</h1>
    </div>
    <div class="header-stats">{summary}</div>
  </header>
  <main>
    <section class="toolbar" aria-label="Deck filters">
      <label class="search-label">
        <span>Search</span>
        <input id="deck-search" type="search" placeholder="Commander, color, or stat">
      </label>
      <div class="color-filter" aria-label="Color identity filter">
        {_color_filter_buttons()}
      </div>
    </section>
    <section id="deck-grid" class="deck-grid">
      {deck_cards}
    </section>
  </main>
  <script id="deck-data" type="application/json">{data}</script>
  <script src="assets/site.js"></script>
</body>
</html>
"""


def render_deck_html(deck: dict, all_decks: Iterable[dict]) -> str:
    stats: DeckStats = deck["stats"]
    sections = "\n".join(_render_section(name, cards) for name, cards in deck["sections"].items())
    commanders = ", ".join(deck["commanders"])
    data = _json_for_script({"cards": deck["cards"]})
    deck_options = "\n".join(
        f'<option value="../decks/{other["slug"]}.html"{ " selected" if other["slug"] == deck["slug"] else ""}>{escape(other["name"])}</option>'
        for other in all_decks
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(deck["name"])} - EDH Decks</title>
  <link rel="stylesheet" href="../assets/site.css">
</head>
<body>
  <header class="deck-hero">
    <nav class="deck-nav">
      <a href="../index.html">All decks</a>
      <select id="deck-jump" aria-label="Open another deck">{deck_options}</select>
    </nav>
    <div class="commander-frame">
      {_commander_images(deck)}
    </div>
    <div class="deck-title">
      <p class="eyebrow">{_color_pips(deck["color_identity"])}</p>
      <h1>{escape(deck["name"])}</h1>
      <p>{escape(commanders)}</p>
    </div>
    <div class="stat-strip">
      {_stat_tile("Power", f"{stats.power_score:.1f}")}
      {_stat_tile("Avg MV", f"{stats.avg_mana_value:.2f}")}
      {_stat_tile("Lands", f"{stats.land_count}/{stats.total_cards}")}
      {_stat_tile("Salt", f"{stats.avg_saltiness:.2f}")}
    </div>
  </header>
  <main class="deck-main">
    <aside class="deck-sidebar">
      <section class="panel">
        <h2>Deck Snapshot</h2>
        {_mini_bars(stats)}
      </section>
      <section class="panel">
        <h2>Mana Curve</h2>
        {_mana_curve(stats)}
      </section>
    </aside>
    <section class="deck-listing">
      <div class="list-heading">
        <h2>Cards</h2>
        <input id="card-search" type="search" placeholder="Search cards">
      </div>
      {sections}
    </section>
  </main>
  <div id="card-preview" class="card-preview" hidden></div>
  <script id="deck-data" type="application/json">{data}</script>
  <script src="../assets/site.js"></script>
</body>
</html>
"""


def copy_site_assets(output_dir: Path) -> None:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(SITE_CSS, encoding="utf-8")
    (assets / "site.js").write_text(SITE_JS, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")


def _build_card_row(
    name: str,
    qty: int,
    is_commander: bool,
    meta: dict,
    image_lookup: Dict[str, str],
    image_output_dir: Path,
) -> dict:
    image = _copy_card_image(name, meta.get("setCode") or "", image_lookup, image_output_dir)
    return {
        "name": name,
        "qty": qty,
        "is_commander": is_commander,
        "section": "Commander" if is_commander else _section_for_type(meta.get("type") or ""),
        "type": meta.get("type") or "",
        "mana_cost": meta.get("manaCost") or "",
        "mana_value": _numeric(meta.get("manaValue")),
        "color_identity": meta.get("colorIdentity") or "",
        "edhrec_rank": _numeric(meta.get("edhrecRank")),
        "salt": _numeric(meta.get("edhrecSaltiness")),
        "is_game_changer": str(meta.get("isGameChanger")).strip().lower() in {"1", "true", "yes"},
        "image": image,
        "scryfall_url": f"https://scryfall.com/search?q={quote('!\"' + name + '\"')}",
    }


def _copy_card_image(name: str, set_code: str, image_lookup: Dict[str, str], image_output_dir: Path) -> str:
    source = image_lookup.get(safe_stem(name))
    if not source:
        return ""
    src_path = Path(source)
    if not src_path.exists():
        return ""
    image_output_dir.mkdir(parents=True, exist_ok=True)

    existing_relative = _relative_to_image_output(src_path, image_output_dir)
    if existing_relative:
        return f"../assets/card-images/{existing_relative.as_posix()}"

    set_folder = safe_stem(set_code).lower() if set_code else "_unknown"
    target = image_output_dir / set_folder / f"{safe_stem(name)}{src_path.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        copy2(src_path, target)
    return f"../assets/card-images/{target.relative_to(image_output_dir).as_posix()}"


def _relative_to_image_output(path: Path, image_output_dir: Path) -> Optional[Path]:
    try:
        return path.resolve().relative_to(image_output_dir.resolve())
    except ValueError:
        return None


def _section_for_type(type_line: str) -> str:
    lowered = (type_line or "").lower()
    for section in SECTION_ORDER:
        if section.lower() in lowered:
            return section
    return "Other"


def _section_cards(cards: List[dict]) -> Dict[str, List[dict]]:
    grouped = defaultdict(list)
    for card in cards:
        grouped[card["section"]].append(card)
    ordered = {}
    for section in SECTION_ORDER:
        values = grouped.get(section)
        if values:
            ordered[section] = sorted(values, key=lambda card: (card["mana_value"] is None, card["mana_value"] or 99, card["name"].lower()))
    return ordered


def _render_deck_card(deck: dict) -> str:
    stats: DeckStats = deck["stats"]
    image = deck["commander_images"][0].removeprefix("../") if deck["commander_images"] else ""
    style = f' style="background-image: linear-gradient(180deg, rgba(16,20,24,.12), rgba(16,20,24,.92)), url(&quot;{escape(image, quote=True)}&quot;)"' if image else ""
    return f"""<article class="deck-card" data-name="{escape(deck["name"].lower(), quote=True)}" data-colors="{escape(deck["color_identity"], quote=True)}"{style}>
  <a href="decks/{deck["slug"]}.html">
    <div class="deck-card-body">
      <div class="deck-card-top">{_color_pips(deck["color_identity"])}</div>
      <h2>{escape(deck["name"])}</h2>
      <div class="deck-card-stats">
        {_stat_tile("Power", f"{stats.power_score:.1f}")}
        {_stat_tile("Avg MV", f"{stats.avg_mana_value:.2f}")}
        {_stat_tile("Lands", str(stats.land_count))}
      </div>
    </div>
  </a>
</article>"""


def _render_section(name: str, cards: List[dict]) -> str:
    rows = "\n".join(_render_card_row(card) for card in cards)
    return f"""<section class="card-section" data-section="{escape(name, quote=True)}">
  <h3>{escape(name)} <span>{sum(card["qty"] for card in cards)}</span></h3>
  <div class="card-table">{rows}</div>
</section>"""


def _render_card_row(card: dict) -> str:
    image_attr = f' data-image="{escape(card["image"], quote=True)}"' if card["image"] else ""
    tags = []
    if card["is_game_changer"]:
        tags.append('<span class="tag">GC</span>')
    if card["salt"] not in (None, 0):
        tags.append(f'<span class="tag">Salt {card["salt"]:.2f}</span>')
    return f"""<a class="card-row" href="{card["scryfall_url"]}" target="_blank" rel="noreferrer" data-card-name="{escape(card["name"].lower(), quote=True)}"{image_attr}>
  <span class="qty">{card["qty"]}x</span>
  <span class="card-name">{escape(card["name"])}</span>
  <span class="mana-cost">{_mana_cost(card["mana_cost"])}</span>
  <span class="type-line">{escape(card["type"])}</span>
  <span class="tags">{''.join(tags)}</span>
</a>"""


def _collection_summary(decks: List[dict]) -> str:
    if not decks:
        return ""
    avg_power = sum(deck["stats"].power_score for deck in decks) / len(decks)
    avg_mv = sum(deck["stats"].avg_mana_value for deck in decks) / len(decks)
    return _stat_tile("Decks", str(len(decks))) + _stat_tile("Avg Power", f"{avg_power:.1f}") + _stat_tile("Avg MV", f"{avg_mv:.2f}")


def _color_filter_buttons() -> str:
    return "".join(f'<button type="button" class="pip-button" data-color="{color}">{color}</button>' for color in COLOR_ORDER)


def _color_pips(identity: str) -> str:
    active = set(re.findall(r"[WUBRG]", identity or ""))
    return "".join(f'<span class="pip pip-{color.lower()}{" active" if color in active else ""}">{color}</span>' for color in COLOR_ORDER)


def _mana_cost(value: str) -> str:
    if not value:
        return ""
    parts = re.findall(r"\{([^}]+)\}", value)
    return "".join(f'<span class="mana-symbol">{escape(part)}</span>' for part in parts)


def _stat_tile(label: str, value: str) -> str:
    return f'<div class="stat-tile"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


def _mini_bars(stats: DeckStats) -> str:
    entries = [
        ("Efficiency", stats.efficiency_score),
        ("Consistency", stats.consistency_score),
        ("Ramp", stats.ramp),
        ("Draw", stats.card_draw),
        ("Removal", stats.spot_removal + stats.counterspells),
        ("Tutors", stats.tutors),
        ("Wipes", stats.board_wipes),
        ("Recursion", stats.recursion),
    ]
    rows = []
    for label, value in entries:
        pct = min(float(value) * 10 if label in {"Efficiency", "Consistency"} else float(value) * 7, 100)
        rows.append(f'<div class="bar-row"><span>{escape(label)}</span><div><i style="width:{pct:.0f}%"></i></div><b>{value:g}</b></div>')
    return "".join(rows)


def _mana_curve(stats: DeckStats) -> str:
    max_count = max(stats.mana_curve.values(), default=1)
    rows = []
    for mv in range(0, max([*stats.mana_curve.keys(), 7]) + 1):
        count = stats.mana_curve.get(mv, 0)
        pct = (count / max_count) * 100 if max_count else 0
        rows.append(f'<div class="curve-row"><span>{mv}</span><div><i style="height:{pct:.0f}%"></i></div><b>{count}</b></div>')
    return f'<div class="mana-curve">{"".join(rows)}</div>'


def _commander_images(deck: dict) -> str:
    images = deck["commander_images"][:2]
    if not images:
        return '<div class="missing-card-art">No commander image</div>'
    return "".join(f'<img src="{escape(image)}" alt="{escape(deck["name"])}">' for image in images)


def _numeric(value: object) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


SITE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #101418;
  --surface: #171d23;
  --surface-2: #202832;
  --line: #2c3642;
  --text: #f3f5f7;
  --muted: #aab4bf;
  --accent: #d9b766;
  --good: #78c6a3;
  --blue: #72a8f2;
  --red: #e77b72;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: inherit; text-decoration: none; }
main { width: min(1440px, calc(100% - 32px)); margin: 0 auto 48px; }
.site-header, .deck-hero {
  width: min(1440px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0;
}
.site-header { display: flex; justify-content: space-between; align-items: end; gap: 24px; }
.eyebrow { margin: 0 0 6px; color: var(--accent); text-transform: uppercase; font-size: 12px; font-weight: 800; letter-spacing: 0; }
h1 { margin: 0; font-size: clamp(34px, 7vw, 72px); line-height: .94; letter-spacing: 0; }
h2, h3 { letter-spacing: 0; }
.header-stats, .stat-strip, .deck-card-stats { display: flex; gap: 8px; flex-wrap: wrap; }
.stat-tile {
  min-width: 88px;
  padding: 8px 10px;
  background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 8px;
}
.stat-tile span { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; font-weight: 800; }
.stat-tile strong { display: block; margin-top: 2px; font-size: 22px; }
.toolbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 0;
  background: rgba(16,20,24,.92);
  backdrop-filter: blur(10px);
}
.search-label { display: flex; align-items: center; gap: 10px; flex: 1; color: var(--muted); font-size: 13px; font-weight: 700; }
input, select {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--text);
  background: var(--surface);
  padding: 8px 10px;
  font: inherit;
}
.color-filter { display: flex; gap: 6px; }
.pip-button {
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: var(--surface);
  color: var(--text);
  font-weight: 900;
  cursor: pointer;
}
.pip-button.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(217,183,102,.24); }
.deck-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
}
.deck-card {
  min-height: 340px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #29323c, #11161b);
  background-size: cover;
  background-position: center 18%;
}
.deck-card a, .deck-card-body { height: 100%; display: block; }
.deck-card-body { display: flex; flex-direction: column; justify-content: space-between; padding: 14px; }
.deck-card h2 { margin: auto 0 12px; font-size: 28px; line-height: 1.02; text-shadow: 0 2px 10px rgba(0,0,0,.75); }
.deck-card-top { align-self: flex-start; padding: 5px 6px; border-radius: 999px; background: rgba(0,0,0,.55); }
.pip {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-right: 3px;
  border-radius: 50%;
  color: #161616;
  background: #3b444e;
  font-size: 11px;
  font-weight: 900;
}
.pip.active.pip-w { background: #f4ecd5; }
.pip.active.pip-u { background: #7fb8ec; }
.pip.active.pip-b { background: #b3a6b6; }
.pip.active.pip-r { background: #e48767; }
.pip.active.pip-g { background: #8fcf8a; }
.deck-hero {
  display: grid;
  grid-template-columns: minmax(210px, 320px) 1fr;
  gap: 22px;
  align-items: end;
}
.deck-nav { grid-column: 1 / -1; display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.deck-nav a { color: var(--accent); font-weight: 800; }
.commander-frame { display: flex; gap: 10px; align-items: end; min-height: 260px; }
.commander-frame img {
  width: min(100%, 300px);
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 18px 40px rgba(0,0,0,.35);
}
.commander-frame img + img { width: min(46%, 190px); margin-left: -60px; }
.deck-title p:last-child { color: var(--muted); margin-bottom: 18px; }
.stat-strip { grid-column: 2; }
.deck-main {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 18px;
  align-items: start;
}
.deck-sidebar { position: sticky; top: 12px; display: grid; gap: 12px; }
.panel {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 8px;
  padding: 14px;
}
.panel h2, .list-heading h2 { margin: 0 0 12px; font-size: 20px; }
.bar-row { display: grid; grid-template-columns: 92px 1fr 36px; gap: 8px; align-items: center; margin: 9px 0; color: var(--muted); font-size: 13px; }
.bar-row div { height: 8px; border-radius: 999px; background: #303a45; overflow: hidden; }
.bar-row i { display: block; height: 100%; background: linear-gradient(90deg, var(--blue), var(--good)); border-radius: inherit; }
.bar-row b { color: var(--text); text-align: right; }
.mana-curve { display: flex; height: 160px; gap: 7px; align-items: end; }
.curve-row { flex: 1; display: grid; grid-template-rows: 18px 1fr 18px; gap: 4px; text-align: center; color: var(--muted); font-size: 12px; }
.curve-row div { display: flex; align-items: end; background: #303a45; border-radius: 6px; overflow: hidden; }
.curve-row i { display: block; width: 100%; min-height: 2px; background: var(--accent); }
.list-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.list-heading input { max-width: 320px; }
.card-section {
  border-top: 1px solid var(--line);
  padding: 12px 0 18px;
}
.card-section h3 { margin: 0 0 8px; font-size: 19px; }
.card-section h3 span { color: var(--muted); font-size: 14px; }
.card-table { display: grid; gap: 4px; }
.card-row {
  display: grid;
  grid-template-columns: 48px minmax(180px, 1.2fr) minmax(90px, auto) minmax(220px, 1fr) minmax(90px, auto);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  padding: 7px 9px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: rgba(255,255,255,.035);
}
.card-row:hover { border-color: rgba(217,183,102,.45); background: rgba(217,183,102,.08); }
.qty { color: var(--muted); font-weight: 800; }
.card-name { font-weight: 800; }
.type-line { color: var(--muted); font-size: 13px; }
.mana-cost { min-height: 24px; }
.mana-symbol {
  display: inline-grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  margin-right: 2px;
  padding: 0 5px;
  border-radius: 50%;
  background: #d9d2c2;
  color: #151515;
  font-size: 11px;
  font-weight: 900;
}
.tags { display: flex; gap: 4px; justify-content: end; flex-wrap: wrap; }
.tag { padding: 3px 6px; border-radius: 999px; background: rgba(217,183,102,.16); color: var(--accent); font-size: 11px; font-weight: 900; }
.card-preview {
  position: fixed;
  left: 0;
  top: 0;
  z-index: 20;
  width: 260px;
  aspect-ratio: 488 / 680;
  border-radius: 12px;
  background-size: cover;
  background-position: center;
  box-shadow: 0 20px 48px rgba(0,0,0,.55);
  pointer-events: none;
}
.missing-card-art {
  display: grid;
  place-items: center;
  width: 260px;
  height: 360px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  color: var(--muted);
}
[hidden] { display: none !important; }
@media (max-width: 900px) {
  .site-header, .toolbar, .deck-hero, .deck-main { display: block; }
  .header-stats, .stat-strip { margin-top: 14px; }
  .toolbar { position: static; }
  .color-filter { margin-top: 10px; }
  .deck-sidebar { position: static; margin-bottom: 18px; }
  .commander-frame { min-height: 0; margin: 12px 0; }
  .card-row { grid-template-columns: 40px 1fr; }
  .mana-cost, .type-line, .tags { grid-column: 2; }
  .tags { justify-content: start; }
}
"""


SITE_JS = r"""
(function () {
  const search = document.getElementById("deck-search");
  const deckGrid = document.getElementById("deck-grid");
  const colorButtons = Array.from(document.querySelectorAll(".pip-button"));
  const activeColors = new Set();

  function normalize(value) {
    return (value || "").toLowerCase();
  }

  function filterDecks() {
    if (!deckGrid) return;
    const query = normalize(search && search.value);
    Array.from(deckGrid.querySelectorAll(".deck-card")).forEach((card) => {
      const haystack = normalize(card.dataset.name + " " + card.dataset.colors);
      const colors = card.dataset.colors || "";
      const matchesText = !query || haystack.includes(query);
      const matchesColors = !activeColors.size || Array.from(activeColors).every((color) => colors.includes(color));
      card.hidden = !(matchesText && matchesColors);
    });
  }

  if (search) search.addEventListener("input", filterDecks);
  colorButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const color = button.dataset.color;
      if (activeColors.has(color)) {
        activeColors.delete(color);
        button.classList.remove("active");
      } else {
        activeColors.add(color);
        button.classList.add("active");
      }
      filterDecks();
    });
  });

  const cardSearch = document.getElementById("card-search");
  if (cardSearch) {
    cardSearch.addEventListener("input", () => {
      const query = normalize(cardSearch.value);
      document.querySelectorAll(".card-row").forEach((row) => {
        row.hidden = query && !normalize(row.dataset.cardName).includes(query);
      });
      document.querySelectorAll(".card-section").forEach((section) => {
        section.hidden = !section.querySelector(".card-row:not([hidden])");
      });
    });
  }

  const preview = document.getElementById("card-preview");
  if (preview) {
    function imageUrl(value) {
      return `url("${String(value).replace(/\\/g, "\\\\").replace(/"/g, "\\\"")}")`;
    }

    document.querySelectorAll(".card-row[data-image]").forEach((row) => {
      row.addEventListener("mouseenter", () => {
        preview.style.backgroundImage = imageUrl(row.dataset.image);
        preview.hidden = false;
      });
      row.addEventListener("mousemove", (event) => {
        const x = Math.min(event.clientX + 22, window.innerWidth - 282);
        const y = Math.min(event.clientY + 22, window.innerHeight - 384);
        preview.style.transform = `translate(${Math.max(12, x)}px, ${Math.max(12, y)}px)`;
      });
      row.addEventListener("mouseleave", () => {
        preview.hidden = true;
      });
    });
  }

  const jump = document.getElementById("deck-jump");
  if (jump) {
    jump.addEventListener("change", () => {
      window.location.href = jump.value;
    });
  }
})();
"""
