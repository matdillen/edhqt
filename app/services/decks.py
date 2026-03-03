from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

import csv
import pandas as pd

INDEX_FILE = Path("data/deck_index.csv")

def sanitize_name(name):
    """Sanitizes names of Split cards and any cards with brackets."""
    def _one(single_name: str) -> str:
        s = single_name.split(" //")[0].strip()
        s = ''.join(s.split("(")[0::2]).strip()
        return s
    if isinstance(name, str):
        return _one(name)
    return [_one(n) for n in name]
    
def refresh_index(decks_folder: Path, lookup_func):
    """Parses all .cod deck XMLs and saves the results to a CSV specified in the INDEX_FILE variable."""
    # Reuse your existing logic to get the dicts
    deck_files, color_ids = index_decks_folder(decks_folder, lookup_func)
    
    with open(INDEX_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["deck_name", "file_path", "color_identity"])
        for name, path in deck_files.items():
            cid = color_ids.get(name, "")
            writer.writerow([name, path, cid])
    
    #print(f"Index refreshed: {len(deck_files)} decks saved.")
    return deck_files, color_ids
    
def load_index(decks_folder: Path, lookup_func, force_reindex=False):
    """Loads the deck index from CSV if it exists, otherwise indexes for the first time. Will reindex if force_reindex is True."""
    if not INDEX_FILE.exists() or force_reindex:
        return refresh_index(decks_folder, lookup_func)
    
    # Fast loading using pandas or csv module
    df = pd.read_csv(INDEX_FILE)
    deck_files = dict(zip(df.deck_name, df.file_path))
    color_ids = dict(zip(df.deck_name, df.color_identity.fillna("")))
    
    return deck_files, color_ids

def index_decks_folder(decks_folder: Path, lookup_color_identity) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Reads the commander name from .cod xml and looks up what its color identity is. Concatenates multiple commanders with the & character. Currently no support for Companions."""
    deck_files: Dict[str, str] = {}
    color_ids: Dict[str, str] = {}

    for file in decks_folder.iterdir():
        if file.suffix.lower() == ".cod":
            try:
                root = ET.parse(file).getroot()
                side_cards = [c.attrib['name'] for c in root.findall("./zone[@name='side']/card")]
                side_cards = sanitize_name(side_cards)
                deck_name = " & ".join(side_cards)
                deck_files[deck_name] = str(file)
                
                # derive deck color identity set from DB lookup
                idset = set()
                for cname in side_cards:
                    cid = lookup_color_identity(cname)
                    if cid:
                        idset.update(cid.split(", "))
                if idset:
                    order = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
                    color_ids[deck_name] = ", ".join(sorted(idset, key=lambda c: order.get(c, 5)))
            except Exception:
            # ignore malformed files but continue
                pass
    return deck_files, color_ids

def read_mainboard(file_path: str) -> List[Tuple[str, int]]:
    """Reads the card names (and counts) in the mainboard of a .cod XML file."""
    root = ET.parse(file_path).getroot()
    out: List[Tuple[str, int]] = []
    for card in root.findall("./zone[@name='main']/card"):
        out.append((card.attrib['name'], int(card.attrib['number'])))
    return out