from typing import Dict, List, Tuple, Optional


def cmc_from_value(mana_value: Optional[str]) -> Optional[int]:
    # returns mana value as int
    if mana_value is None or mana_value == "":
        return None
    try:
        return int(float(mana_value))
    except Exception:
        return None