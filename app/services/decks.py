from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

def sanitize_name(name):
    # sanitizes split card names and any cards with brackets
    def _one(single_name: str) -> str:
        s = single_name.split(" //")[0].strip()
        s = ''.join(s.split("(")[0::2]).strip()
        return s
    if isinstance(name, str):
        return _one(name)
    return [_one(n) for n in name]

def index_decks_folder(decks_folder: Path, lookup_color_identity) -> Tuple[Dict[str, str], Dict[str, str]]:
    # reads deck content from .cod xml, using the card(s) in side (i.e. the commander(s)) as name
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
    root = ET.parse(file_path).getroot()
    out: List[Tuple[str, int]] = []
    for card in root.findall("./zone[@name='main']/card"):
        out.append((card.attrib['name'], int(card.attrib['number'])))
    return out