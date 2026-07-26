import sqlite3
import json
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
            "setCode, power, toughness, manaCost, producedMana, "
            "edhrecRank, edhrecSaltiness, isGameChanger"
        )
        res = self.query_one(SELECT, "cards", "name = ?", (card_name,))
        if not res:
            res = self.query_one(SELECT, "cards", "faceName = ?", (card_name,))
        if not res:
            return {
                "subtypes": "",
                "manaValue": None,
                "type": "",
                "colorIdentity": "",
                "text": "",
                "setCode": "",
                "power": "",
                "toughness": "",
                "manaCost": "",
                "producedMana": "",
                "edhrecRank": None,
                "edhrecSaltiness": 0.0,
                "isGameChanger": 0,
            }
        keys = [
            "subtypes", "manaValue", "colorIdentity", "type", "text",
            "setCode", "power", "toughness", "manaCost", "producedMana",
            "edhrecRank", "edhrecSaltiness", "isGameChanger",
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

    def fetch_token_from_db(self, token_name: str) -> dict:
        """Look up token metadata by token name."""
        SELECT = (
            "subtypes, colorIdentity, type, text, setCode, power, toughness, "
            "manaCost, producedMana, edhrecSaltiness"
        )
        res = self.query_one(SELECT, "tokens", "name = ?", (token_name,))
        if not res:
            return {
                "subtypes": "",
                "colorIdentity": "",
                "type": "Token",
                "text": "",
                "setCode": "",
                "power": "",
                "toughness": "",
                "manaCost": "",
                "producedMana": "",
                "edhrecSaltiness": "",
            }
        keys = [
            "subtypes", "colorIdentity", "type", "text", "setCode", "power",
            "toughness", "manaCost", "producedMana", "edhrecSaltiness",
        ]
        return dict(zip(keys, res))

    def fetch_token_by_uuid(self, token_uuid: str) -> dict:
        """Look up token metadata by MTGJSON token UUID."""
        SELECT = (
            "name, subtypes, colorIdentity, type, text, setCode, power, toughness, "
            "manaCost, producedMana, edhrecSaltiness, uuid"
        )
        res = self.query_one(SELECT, "tokens", "uuid = ?", (token_uuid,))
        if not res:
            return {}
        keys = [
            "name", "subtypes", "colorIdentity", "type", "text", "setCode",
            "power", "toughness", "manaCost", "producedMana", "edhrecSaltiness",
            "uuid",
        ]
        return dict(zip(keys, res))

    def fetch_related_tokens_for_card(self, card_name: str) -> list[dict]:
        """Return token rows linked from a card's relatedCards JSON."""
        return self.fetch_related_tokens_for_cards([card_name]).get(card_name, [])

    def _token_uuids_from_related_rows(self, rows) -> list[str]:
        """Extract distinct token UUIDs from relatedCards rows."""
        token_uuids = []
        seen_uuids = set()
        for raw_related in rows:
            if not raw_related:
                continue
            try:
                related = json.loads(raw_related)
            except (TypeError, ValueError):
                continue
            for token_uuid in related.get("tokens") or []:
                if token_uuid in seen_uuids:
                    continue
                seen_uuids.add(token_uuid)
                token_uuids.append(token_uuid)
        return token_uuids

    def _fetch_tokens_by_uuid(self, token_uuids: list[str]) -> dict[str, dict]:
        """Fetch many token rows by UUID."""
        if not token_uuids:
            return {}
        SELECT = (
            "name, subtypes, colorIdentity, type, text, setCode, power, toughness, "
            "manaCost, producedMana, edhrecSaltiness, uuid"
        )
        keys = [
            "name", "subtypes", "colorIdentity", "type", "text", "setCode",
            "power", "toughness", "manaCost", "producedMana", "edhrecSaltiness",
            "uuid",
        ]
        out = {}
        cur = self.conn.cursor()
        for index in range(0, len(token_uuids), 500):
            chunk = token_uuids[index:index + 500]
            placeholders = ",".join("?" for _ in chunk)
            cur.execute(f"SELECT {SELECT} FROM tokens WHERE uuid IN ({placeholders})", chunk)
            for row in cur.fetchall():
                token = dict(zip(keys, row))
                out[token["uuid"]] = token
        return out

    def fetch_related_tokens_for_cards(self, card_names: list[str]) -> dict[str, list[dict]]:
        """Return token rows linked from each card's relatedCards JSON."""
        requested = [name for name in dict.fromkeys(card_names) if name]
        if not requested:
            return {}

        related_by_card = {name: [] for name in requested}
        requested_set = set(requested)
        cur = self.conn.cursor()
        for index in range(0, len(requested), 500):
            chunk = requested[index:index + 500]
            placeholders = ",".join("?" for _ in chunk)
            cur.execute(
                f"""
                SELECT name, faceName, relatedCards
                FROM cards
                WHERE name IN ({placeholders}) OR faceName IN ({placeholders})
                """,
                chunk + chunk,
            )
            for row_name, face_name, raw_related in cur.fetchall():
                if not raw_related:
                    continue
                matched_names = []
                if row_name in requested_set:
                    matched_names.append(row_name)
                if face_name in requested_set:
                    matched_names.append(face_name)
                for matched_name in matched_names:
                    related_by_card[matched_name].append(raw_related)

        uuids_by_card = {
            card_name: self._token_uuids_from_related_rows(rows)
            for card_name, rows in related_by_card.items()
        }
        all_uuids = []
        seen_uuids = set()
        for token_uuids in uuids_by_card.values():
            for token_uuid in token_uuids:
                if token_uuid in seen_uuids:
                    continue
                seen_uuids.add(token_uuid)
                all_uuids.append(token_uuid)
        tokens_by_uuid = self._fetch_tokens_by_uuid(all_uuids)

        return {
            card_name: [
                tokens_by_uuid[token_uuid]
                for token_uuid in token_uuids
                if token_uuid in tokens_by_uuid
            ]
            for card_name, token_uuids in uuids_by_card.items()
        }
