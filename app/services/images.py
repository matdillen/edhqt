from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
import os
import time
import requests
import csv
import re

# scryfall API endpoint for exact name lookup
SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
# Default app image cache directory
APP_IMG_CACHE = Path("data/img")
APP_IMG_INDEX = "data/img_index.csv"
COCKATRICE_CACHE_IMPORT = APP_IMG_CACHE / "cockatrice-cache"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF", ".webp"),
)

def ensure_app_cache_dir(path: Optional[Path] = None) -> Path:
    """Ensure the app's own image cache directory exists and return it."""
    cache_dir = Path(path) if path else APP_IMG_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def safe_stem(name: str) -> str:
    # Lowercase, strip slashes and problematic chars for filesystem
    stem = (name or "").strip().lower()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        stem = stem.replace(ch, " ")
    stem = " ".join(stem.split())
    return stem or "card"

def fetch_image_from_scryfall(card_name: str, size: str = "normal", session: Optional[requests.Session] = None) -> Optional[bytes]:
    """Fetch a card image from Scryfall by exact name. Returns image bytes or None.
    Respects simple backoff on HTTP 429/503.
    """
    if not requests:
        return None
    sess = session or requests.Session()
    params = {"exact": card_name, "format": "json"}
    backoff = [0.0, 0.5, 1.0, 2.0]
    for delay in backoff:
        try:
            r = sess.get(SCRYFALL_NAMED_URL, params=params, timeout=20)
            if r.status_code in (429, 503):
                time.sleep(delay)
                continue
            r.raise_for_status()
            data = r.json()
            # Single-faced vs MDFC
            url = None
            if "image_uris" in data and data["image_uris"]:
                url = data["image_uris"].get(size) or data["image_uris"].get("large")
            elif "card_faces" in data and data["card_faces"]:
                face = data["card_faces"][0]
                if "image_uris" in face:
                    url = face["image_uris"].get(size) or face["image_uris"].get("large")
            if not url:
                return None
            ir = sess.get(url, timeout=30)
            if ir.status_code in (429, 503):
                time.sleep(delay)
                continue
            ir.raise_for_status()
            return ir.content
        except Exception:
            time.sleep(delay)
        continue
    return None

def cache_image_for_card(card_name: str, cache_dir: Optional[Path] = None, size: str = "normal") -> Optional[Path]:
    """Ensure an image for card_name exists in the app cache; download if missing.
    Returns the cached image path or None on failure.
    """
    cache_dir = ensure_app_cache_dir(cache_dir)
    stem = safe_stem(card_name)
    # If any existing extension is present, reuse it
    for p in cache_dir.glob(stem + ".*"):
        if p.is_file():
            return p


    img_bytes = fetch_image_from_scryfall(card_name, size=size)
    if not img_bytes:
        return None


    # default extension is .jpg
    ext = ".jpg"

    out_path = cache_dir / f"{stem}{ext}"
    try:
        out_path.write_bytes(img_bytes)
        return out_path
    except Exception:
        return None

def build_image_lookup(primary_dir: Path, app_cache_dir: Optional[Path] = APP_IMG_CACHE) -> Dict[str, str]:
    """Walk both the user-provided image folder and the app's own cache.
    Returns a map: lowercased card name stem → absolute file path.
    """
    lookup: Dict[str, str] = {}


    import_dir = ensure_app_cache_dir(COCKATRICE_CACHE_IMPORT) if app_cache_dir else None

    def _scan(folder: Optional[Path], extract_cockatrice_cache: bool = True):
        if not folder:
            return
        folder = Path(folder)
        if not folder.exists():
            return
        for root, _, files in os.walk(folder):
            for f in files:
                lf = f.lower()
                path = Path(root) / f
                if lf.endswith(IMAGE_SUFFIXES):
                    name = safe_stem(os.path.splitext(f)[0])
                    lookup[name] = str(path)
                elif extract_cockatrice_cache and lf.endswith(".d") and import_dir:
                    imported = import_cockatrice_cache_file(path, import_dir)
                    if imported:
                        name, image_path = imported
                        lookup[name] = str(image_path)


    # 1) User-provided folder from config
    _scan(primary_dir)


    # 2) App's own cache
    _scan(ensure_app_cache_dir(app_cache_dir), extract_cockatrice_cache=False)


    return lookup


def build_image_lookup_from_dirs(source_dirs: Iterable[Optional[Path]], app_cache_dir: Optional[Path] = APP_IMG_CACHE) -> Dict[str, str]:
    """Build a single image lookup from several image/cache roots."""
    lookup: Dict[str, str] = {}
    for source_dir in source_dirs:
        if source_dir:
            lookup.update(build_image_lookup(Path(source_dir), app_cache_dir=app_cache_dir))
    return lookup


def import_cockatrice_cache_file(cache_file: Path, output_dir: Path = COCKATRICE_CACHE_IMPORT) -> Optional[Tuple[str, Path]]:
    """Extract an image embedded in a Cockatrice/Qt network cache .d file.

    Cockatrice stores Scryfall HTTP responses as Qt cache entries: metadata first,
    then the raw image payload. The leading metadata means QPixmap and browsers
    should not read the .d file directly, so this normalizes it into a regular
    image file and returns (safe card key, image path).
    """
    try:
        raw = Path(cache_file).read_bytes()
    except OSError:
        return None

    filename = _cache_content_filename(raw)
    if not filename:
        return None

    image_offset, extension = _embedded_image_offset(raw)
    if image_offset < 0:
        return None

    set_code, card_key = _card_key_from_cache_filename(filename)
    if not card_key:
        return None

    target_dir = output_dir / safe_stem(set_code or "_unknown")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{card_key}{extension}"
    if not target.exists():
        target.write_bytes(raw[image_offset:])
    return card_key, target


def _embedded_image_offset(raw: bytes) -> Tuple[int, str]:
    found = [item for item in ((raw.find(signature), extension) for signature, extension in IMAGE_SIGNATURES) if item[0] >= 0]
    if not found:
        return -1, ""
    return min(found, key=lambda item: item[0])


def _cache_content_filename(raw: bytes) -> str:
    match = re.search(rb'filename="?([^"\x00\r\n;]+)"?', raw)
    if not match:
        return ""
    try:
        return match.group(1).decode("utf-8")
    except UnicodeDecodeError:
        return match.group(1).decode("cp1252", errors="ignore")


def _card_key_from_cache_filename(filename: str) -> Tuple[str, str]:
    stem = Path(filename).stem.strip().lower()
    pieces = [piece for piece in stem.split("-") if piece]
    if len(pieces) < 3:
        return "", safe_stem(stem)

    set_code = pieces[0]
    collector_end = 1
    while collector_end + 1 < len(pieces) and _looks_like_collector_piece(pieces[collector_end + 1]):
        collector_end += 1

    card_name = " ".join(pieces[collector_end + 1:])
    return set_code, safe_stem(card_name)


def _looks_like_collector_piece(piece: str) -> bool:
    return bool(re.fullmatch(r"[a-z]*\d+[a-z]*|[a-z]", piece or ""))

def get_image_lookup(source_directory: Optional[object] = None) -> Dict[str, str]:
    """
    Retrieves a lookup dictionary from a CSV. If a source_directory is provided,
    it regenerates the lookup and updates the CSV file.
    """
    
    # Scenario A: Update the CSV with new data from build_image_lookup
    if source_directory:
        if isinstance(source_directory, (str, Path)):
            image_lookup = build_image_lookup(Path(source_directory))
        else:
            image_lookup = build_image_lookup_from_dirs(source_directory)
        
        with open(APP_IMG_INDEX, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Writing the dictionary items as rows
            for key, path in image_lookup.items():
                writer.writerow([key, path])
        
        return image_lookup

    # Scenario B: Simply read the existing CSV
    image_lookup = {}
    try:
        with open(APP_IMG_INDEX, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 2:
                    key, path = row
                    image_lookup[key] = path
    except FileNotFoundError:
        # Return an empty dict if the file doesn't exist yet
        return {}

    return image_lookup
        
