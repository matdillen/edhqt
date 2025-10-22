from typing import Dict, List, Tuple, Optional


def cmc_from_value(mana_value: Optional[str]) -> Optional[int]:
    # returns mana value as int
    if mana_value is None or mana_value == "":
        return None
    try:
        return int(float(mana_value))
    except Exception:
        return None

def mana_curve(deck_cards: List[Tuple[str, int]], cache_lookup) -> Dict[int, int]:
    # saves a mana curve based on cardname lookup, ignoring nonstandard values
    curve: Dict[int, int] = {}
    for card_name, qty in deck_cards:
        data = cache_lookup(card_name.lower())
        if not data:
            continue
        cmc = cmc_from_value(data.get("manaValue"))
        if cmc is not None:
            curve[cmc] = curve.get(cmc, 0) + qty
    return curve