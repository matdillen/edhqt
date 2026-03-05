import sqlite3
from typing import Tuple, Any

class CardDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)

    def query_one(self, select_clause: str, from_clause: str, where_clause: str, params: Tuple[Any, ...]):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {select_clause} FROM {from_clause} WHERE {where_clause}", params)
        return cur.fetchone()
    
    def query_all(self, select_clause: str, from_clause: str, where_clause: str, params: Tuple[Any, ...]):
        cur = self.conn.cursor()
        cur.execute(f"SELECT DISTINCT {select_clause} FROM {from_clause} WHERE {where_clause}", params)
        return cur.fetchall()
    
    def fetch_card_from_db(self, card_name: str) -> dict:
        """Query the database by name, fallback for faceName; fetch all fields we currently display or search on."""
        SELECT = (
            "subtypes, manaValue, colorIdentity, type, text, "
            "setCode, power, toughness"
        )
        res = self.query_one(SELECT, "cards", "name = ?", (card_name,))
        if not res:
            res = self.query_one(SELECT, "cards", "faceName = ?", (card_name,))
        if not res:
            return {"subtypes": "", "manaValue": None, "type": "", "colorIdentity": "", "text": "", "setCode": "", "power": "", "toughness": ""}
        keys = [
            "subtypes", "manaValue", "colorIdentity", "type", "text",
            "setCode", "power", "toughness",
        ]
        return dict(zip(keys, res))
    
    def lookup_cid(self, card_name: str):
        """Looks up color identity in the sqlite database based on card name, or facename as a fallback for DFCs."""
        res = self.query_one("colorIdentity", "cards", "name = ?", (card_name,))
        if not res or not res[0]:
            res = self.query_one("colorIdentity", "cards", "faceName = ?", (card_name,))
        return res[0] if res else ""
    
    def list_game_changers(self):
        """Return a simple list of game changer card names."""
        res = self.query_all("name", "cards", "isGameChanger = ?", (1,))
        return [r[0] for r in res]