import sqlite3
from typing import Optional, Tuple, Any

class CardDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)


    def query_one(self, select_clause: str, from_clause: str, where_clause: str, params: Tuple[Any, ...]):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {select_clause} FROM {from_clause} WHERE {where_clause}", params)
        return cur.fetchone()