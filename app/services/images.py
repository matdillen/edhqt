from pathlib import Path
from typing import Dict
import os

def build_image_lookup(image_folder: Path) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for root, _, files in os.walk(image_folder):
        for f in files:
            if f.lower().endswith(".jpg"):
                name = os.path.splitext(f)[0]
                lookup[name.lower()] = str(Path(root) / f)
    return lookup