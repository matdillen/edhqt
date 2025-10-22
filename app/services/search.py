import csv
from pathlib import Path
from typing import Dict, Any, List, Tuple

class CardCache:
    def __init__(self, path: Path):
        self.path = path
        self.cache: Dict[str, Dict[str, Any]] = {}
        # Remember original encoding if we successfully detect it on load
        self._detected_encoding: str | None = None
        
    def _try_open(self, mode: str, enc: str):
        return self.path.open(mode, encoding=enc, newline="")
        
    def load(self):
        if not self.path.exists():
            return
        # Be tolerant: try UTF-8 first, then Windows-1252 (ANSI on many Windows locales),
        # and finally a permissive UTF-8 decode with replacement.
        encodings = ["utf-8-sig", "utf-8", "cp1252"]
        last_err = None
        for enc in encodings:
            try:
                with self._try_open("r", enc) as f:
                    r = csv.DictReader(f)
                    for row in r:
                        name = (row.get("name") or "").lower()
                        if not name:
                            continue
                        self.cache[name] = {
                            "subtypes": row.get("subtypes", ""),
                            "manaValue": row.get("manaValue", ""),
                            "colorIdentity": row.get("colorIdentity", ""),
                        }
                self._detected_encoding = enc
                return
            except UnicodeError as e:
                last_err = e
                # fall through to next encoding
        # Last resort: read bytes and decode with replacement to avoid crash
        try:
            raw = self.path.read_bytes().decode("utf-8", errors="replace")
            from io import StringIO
            r = csv.DictReader(StringIO(raw))
            for row in r:
                name = (row.get("name") or "").lower()
                if not name:
                    continue
                self.cache[name] = {
                    "subtypes": row.get("subtypes", ""),
                    "manaValue": row.get("manaValue", ""),
                    "colorIdentity": row.get("colorIdentity", ""),
                }
            self._detected_encoding = "utf-8"
        except Exception as e:
            # re-raise original Unicode error if present for better debugging
            raise last_err or e

    def save(self):
        with self.path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "subtypes", "manaValue", "colorIdentity"])
            w.writeheader()
            for name, data in self.cache.items():
                w.writerow({
                "name": name,
                "subtypes": data.get("subtypes", ""),
                "manaValue": data.get("manaValue", ""),
                "colorIdentity": data.get("colorIdentity", ""),
            })


    def ensure_card(self, name_lc: str, fetch_fn):
        if name_lc in self.cache:
            return self.cache[name_lc]
        data = fetch_fn()
        if data:
            self.cache[name_lc] = data
        return data

def search_in_deck(deck_cards: List[Tuple[str, int]], query: str, cache: CardCache, mode: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    qparts = [q.strip() for q in query.lower().split(',') if q.strip()]
    for card_name, qty in deck_cards:
        if mode == "Cards":
            if query in card_name.lower():
                out.append((card_name, qty))
        else: # Subtypes
            data = cache.cache.get(card_name.lower())
            if data:
                st = (data.get("subtypes") or "").lower()
                if any(p in st for p in qparts):
                    out.append((card_name, qty))
    return out