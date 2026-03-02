import json
from pathlib import Path

class AppConfig:
    def __init__(self, decks_folder: str, db_path: str, image_folder: str, cache_file: str):
        # path to dir with .cod deck files
        self.decks_folder = Path(decks_folder)
        # path to sqlite db file
        self.db_path = Path(db_path)
        # path to folder with saved scryfall images, using cockatrice's old caching system
        self.image_folder = Path(image_folder)
        # path to csv file with cached card data
        self.cache_file = Path(cache_file)

    @classmethod
    def load(cls, path: str = "app/config.json"):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cls(
            decks_folder=cfg.get("decks_folder", "./decks"),
            db_path=cfg.get("db_path", "./allprintings.sqlite"),
            image_folder=cfg.get("image_folder", "./images"),
            cache_file=cfg.get("cache_file", "./card_cache.csv")
        )