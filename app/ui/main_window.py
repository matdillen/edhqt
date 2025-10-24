from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QComboBox, QLineEdit, QPushButton, QLabel, QMessageBox, QSizePolicy, QProgressDialog
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from app.services.config import AppConfig
from app.services.db import CardDB
from app.services.decks import index_decks_folder, read_mainboard
from app.services.images import build_image_lookup, cache_image_for_card, safe_stem
from app.services.search import CardCache, search_in_deck
from app.services.analytics import mana_curve
from app.services.visualize import manafy_html
from app.ui.plane_view import DeckPlaneDialog

from typing import Optional
from string import Template
from pathlib import Path

import os

class CardRowWidget(QWidget):
    """A richer row for deck cards with color pips, qty, name, and mana value."""
    def __init__(self, name: str, qty: int, color_identity: str, mana_value: Optional[str]):
        super().__init__()
        self.name = name
        self.qty = qty
        self.color_identity = color_identity or ""
        self.mana_value = mana_value

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        # Color pips
        self.pips = QLabel()
        self.pips.setTextInteractionFlags(Qt.NoTextInteraction)
        lay.addWidget(self.pips)

        # Qty chip
        self.qty_lbl = QLabel(f"{qty}×")
        self.qty_lbl.setStyleSheet("QLabel { padding: 2px 6px; border-radius: 8px; border: 1px solid #666; }")
        lay.addWidget(self.qty_lbl)

        # Name
        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet("QLabel { font-weight: 600; }")
        self.name_lbl.setTextInteractionFlags(Qt.NoTextInteraction)
        lay.addWidget(self.name_lbl, 1)

        # Mana value chip
        mv_text = str(int(float(mana_value))) if (mana_value not in (None, "")) else "—"
        self.mv_lbl = QLabel(mv_text)
        self.mv_lbl.setStyleSheet("QLabel { padding: 2px 6px; border-radius: 8px; background: #2a2a2a; color: #ddd; }")
        self.mv_lbl.setAlignment(Qt.AlignCenter)
        self.mv_lbl.setFixedWidth(28)
        lay.addWidget(self.mv_lbl)

    def set_pips_html(self, html: str):
        self.pips.setText(html)


class AutoSelectTextEdit(QLineEdit):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTG Deck Analyzer")
        self.setGeometry(100, 100, 1000, 600)

        # Config & services
        self.config = AppConfig.load()
        self.db = CardDB(str(self.config.db_path))
        self.image_lookup = build_image_lookup(self.config.image_folder)
        self.cache = CardCache(self.config.cache_file)
        self.cache.load()

        # color identity lookup uses both name and faceName as in your script
        def lookup_cid(card_name: str):
            res = self.db.query_one("colorIdentity", "cards", "name = ?", (card_name,))
            if not res or not res[0]:
                res = self.db.query_one("colorIdentity", "cards", "faceName = ?", (card_name,))
            return res[0] if res else ""

        self.deck_files, self.color_ids = index_decks_folder(self.config.decks_folder, lookup_cid)
        self.deck_files_actu = dict(self.deck_files)

        # UI layout
        main_layout = QHBoxLayout()

        # Left panel: deck list + filters
        left_layout = QVBoxLayout()

        self.deck_list = QListWidget()
        left_layout.addWidget(self.deck_list)
        self._init_decklist_items(self.deck_files)
        self.deck_list.itemClicked.connect(self._load_deck_clicked)

        s_layout = QHBoxLayout()
        self.search_dropdown = QComboBox(); self.search_dropdown.addItems(["Cards", "Subtypes"])
        s_layout.addWidget(self.search_dropdown)
        self.search_input = AutoSelectTextEdit(self); self.search_input.setPlaceholderText("Search for a card or subtype")
        self.search_input.returnPressed.connect(self._search_decks)
        s_layout.addWidget(self.search_input)
        btn = QPushButton("Search Decks"); btn.clicked.connect(self._search_decks)
        s_layout.addWidget(btn)
        left_layout.addLayout(s_layout)

        f_layout = QHBoxLayout()
        self.filter_dropdown = QComboBox(); self.filter_dropdown.addItems(["Color Identity"])  # extensible
        f_layout.addWidget(self.filter_dropdown)
        self.filter_input = QLineEdit(); self.filter_input.setPlaceholderText("Filter for color(s), e.g. wub")
        self.filter_input.returnPressed.connect(self._filter_decks)
        f_layout.addWidget(self.filter_input)
        f_btn = QPushButton("Filter Decks"); f_btn.clicked.connect(self._filter_decks)
        f_layout.addWidget(f_btn)
        r_btn = QPushButton("Reset Filter"); r_btn.clicked.connect(self._reset_deck_list)
        f_layout.addWidget(r_btn)
        plane_btn = QPushButton("Deck Plane"); plane_btn.clicked.connect(self._show_deck_plane)
        f_layout.addWidget(plane_btn)
        left_layout.addLayout(f_layout)

        main_layout.addLayout(left_layout,stretch=1)

        # Mid panel: deck contents
        mid_layout = QVBoxLayout()
        self.deck_display = QListWidget(); self.deck_display.itemClicked.connect(self._show_card_details)
        mid_layout.addWidget(self.deck_display)

        main_layout.addLayout(mid_layout,stretch=2)

        # Right panel: card details
        right_layout = QVBoxLayout()
        self.card_image_label = QLabel("Card Image"); self.card_image_label.setAlignment(Qt.AlignCenter)
        self.card_image_label.setStyleSheet("border: 1px solid black;")
        self.card_image_label.mousePressEvent = self._show_image_popup
        right_layout.addWidget(self.card_image_label, 1)

        self.card_text_display = QLabel("Card Details"); self.card_text_display.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.card_text_display.setStyleSheet("border: 1px solid black;")
        self.card_text_display.setWordWrap(True)
        self.card_text_display.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_layout.addWidget(self.card_text_display, 1)

        #right_layout.addLayout(bottom)
        main_layout.addLayout(right_layout,stretch=2)

        # Central widget
        cw = QWidget(); cw.setLayout(main_layout)
        self.setCentralWidget(cw)

        # State
        self.current_card_image_path = None
        self.current_deck_cards = []

    # ---------- UI helpers ----------
    def _color_hex(self, c: str) -> str:
        return {"W":"#FFFFFF","U":"#0000FF","B":"#000000","R":"#FF0000","G":"#008000"}.get(c, "#202124")

    def _fetch_card_from_db(self, card_name: str) -> dict:
    # Query by name, fallback faceName; fetch all fields we display or search on
        SELECT = (
            "subtypes, manaValue, colorIdentity, type, text, "
            "setCode, power, toughness"
        )
        res = self.db.query_one(SELECT, "cards", "name = ?", (card_name,))
        if not res:
            res = self.db.query_one(SELECT, "cards", "faceName = ?", (card_name,))
        if not res:
            return {"subtypes": "", "manaValue": None, "type": "", "colorIdentity": "", "text": "", "setCode": "", "power": "", "toughness": ""}
        keys = [
            "subtypes", "manaValue", "colorIdentity", "type", "text",
            "setCode", "power", "toughness",
        ]
        return dict(zip(keys, res))
    
    def _get_card(self, card_name: str) -> dict:
        key = (card_name or "").lower()
        if not key:
            return {}
        def fetch():
            data = self._fetch_card_from_db(card_name) or {}
            return data
        data = self.cache.ensure_card(key, fetch) or {}
        # Persist new cache entries ASAP so subsequent screens are instant
        self.cache.save()
        return data
    
    def _init_decklist_items(self, decks):
        self.deck_list.clear()
        order = ["W","U","B","R","G"]
        for deck_name in decks:
            identity = self.color_ids.get(deck_name, "")
            squares = " ".join([f'<span style="color:{self._color_hex(c) if c in identity else "#202124"};">&#9632;</span>' for c in order])

            item_widget = QWidget(); lay = QHBoxLayout(); lay.setContentsMargins(5,5,5,5)
            color_lbl = QLabel(); color_lbl.setText(squares); color_lbl.setAlignment(Qt.AlignLeft)
            name_lbl = QLabel(deck_name); name_lbl.setAlignment(Qt.AlignLeft)
            lay.addWidget(color_lbl); lay.addWidget(name_lbl); lay.addStretch(); item_widget.setLayout(lay)

            item = QListWidgetItem(self.deck_list)
            item.setSizeHint(item_widget.sizeHint())
            self.deck_list.addItem(item)
            self.deck_list.setItemWidget(item, item_widget)

    def _selected_deck_name(self):
        item = self.deck_list.currentItem()
        if not item:
            return None
        return self.deck_list.itemWidget(item).layout().itemAt(1).widget().text().split(" (")[0]

    # ---------- Actions ----------
    def _load_deck_clicked(self, item):
        dn = self.deck_list.itemWidget(item).layout().itemAt(1).widget().text().split(" (")[0]
        self._load_deck_by_name(dn)

    def _load_deck_by_name(self, deck_name: str):
        file_path = self.deck_files.get(deck_name)
        if not file_path:
            return
        self.current_deck_cards = read_mainboard(file_path)

        # fill cache for missing cards (subtypes, manaValue)
        for cname, _ in self.current_deck_cards:
            self._get_card(cname)

        self._display_deck(self.current_deck_cards)

    def _pip_squares(self, identity: str) -> str:
        order = ["W", "U", "B", "R", "G"]
        squares = []
        for c in order:
            active = (c in (identity or ""))
            col = self._color_hex(c) if active else "#3a3a3a"
            squares.append(f'<span style="color:{col}; font-size:14px;">&#9632;</span>')
        return " ".join(squares)

    def _display_deck(self, deck_cards):
        self.deck_display.clear()
        for name, qty in deck_cards:
            meta = self._get_card(name)
            mv = meta.get("manaValue")
            ci = meta.get("colorIdentity") or ""
            row = CardRowWidget(name=name, qty=qty, color_identity=ci, mana_value=mv)
            row.set_pips_html(self._pip_squares(ci))

            item = QListWidgetItem()
            item.setData(Qt.UserRole, name)
            item.setSizeHint(row.sizeHint())
            self.deck_display.addItem(item)
            self.deck_display.setItemWidget(item, row)

    def _search_decks(self):
        query = (self.search_input.text() or "").strip().lower()
        if not query:
            return
        results = []
        for deck_name, path in self.deck_files_actu.items():
            cards = read_mainboard(path)
            matches = search_in_deck(cards, query, self.cache, self.search_dropdown.currentText())
            if matches:
                results.append((deck_name, matches))
        if not results:
            self.deck_display.clear(); self.deck_display.addItem(f"No results found for query: {query}")
            return
        self._display_search_results(results)

    def _display_search_results(self, results):
        self.deck_display.clear()
        for deck_name, cards in results:
            self.deck_display.addItem(f"Deck: {deck_name}")
            for card_name, qty in cards:
                self.deck_display.addItem(f"    {qty}x {card_name}")

    def _reset_deck_list(self):
        self.deck_files_actu = dict(self.deck_files)
        self._init_decklist_items(self.deck_files)

    def _filter_decks(self):
        query = (self.filter_input.text() or "").strip().lower()
        if not query:
            return
        filtered = {}
        for deck_name, identity in self.color_ids.items():
            raw = set([x.lower() for x in identity.split(', ') if x])
            if all(ch in raw for ch in query):
                filtered[deck_name] = self.deck_files[deck_name]
        self.deck_files_actu = filtered
        self._init_decklist_items(filtered)

    def _show_card_details(self, item):
        # Retrieve the card name stored in UserRole (since rows are custom widgets)
        card_name = item.data(Qt.UserRole)
        if not card_name:
            # Fallback: try to parse from text if present
            text = item.text() or ""
            card_name = text.split("x ", 1)[-1].strip()
        key = (card_name or "").lower()

        # Image
        img = self.image_lookup.get(key)
        if not img:
            cached_path = cache_image_for_card(card_name)
            if cached_path:
                # Rebuild lookup so subsequent selections are instant
                self.image_lookup[safe_stem(card_name)] = str(cached_path)
                img = str(cached_path)

        if img:
            self.card_image_label.setPixmap(QPixmap(img).scaled(200, 300, Qt.KeepAspectRatio, transformMode=Qt.SmoothTransformation))
            self.current_card_image_path = img
        else:
            self.card_image_label.clear(); self.card_image_label.setText("Image not available")

        # Metadata
        meta = self._get_card(card_name)
        mv = meta.get("manaValue")
        mv_txt = str(int(float(mv))) if (mv not in (None, "")) else "—"
        type_line = meta.get("type") or ""
        oracle = (meta.get("text") or "").replace("\\n","<br>")
        oracle = manafy_html(oracle)
        set_code = meta.get("setCode") or ""
        power = meta.get("power") or ""
        toughness = meta.get("toughness") or ""
        ci = meta.get("colorIdentity") or ""
        
        power_html = f"<div class='stat'>Power: {power}</div>" if power else ""
        toughness_html = f"<div class='stat'>Toughness: {toughness}</div>" if toughness else ""
        
        template_path = Path(__file__).parent.parent / "views" / "card_details.html"
        template_text = template_path.read_text(encoding="utf-8")
        
        style_path = template_path.parent / "style.css"
        style_text = style_path.read_text(encoding="utf-8")

        html = f"<style>{style_text}</style>\n" + Template(template_text).safe_substitute(
            card_name=card_name,
            pips_html=self._pip_squares(ci),
            mv_txt=mv_txt,
            set_code=set_code,
            type_line=type_line,
            oracle_html=oracle,
            power_html=power_html,
            toughness_html=toughness_html,
        )
        self.card_text_display.setText(html)

    def _show_image_popup(self, _evt):
        if not self.current_card_image_path:
            return
        popup = QMessageBox(); popup.setWindowTitle("Card Image")
        pix = QPixmap(self.current_card_image_path)
        popup.setIconPixmap(pix.scaledToHeight(680))
        popup.exec()

    def _ensure_deck_images(self, deck_cards):
        missing = []
        for name, _ in deck_cards:
            key = safe_stem(name)
            path = self.image_lookup.get(key)
            if not path or not os.path.exists(path):
                missing.append(name)
        if not missing:
            return

        dlg = QProgressDialog("Fetching images…", "Cancel", 0, len(missing), self)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumDuration(300)

        for i, cname in enumerate(missing):
            if dlg.wasCanceled():
                break
            p = cache_image_for_card(cname)
            if p:
                self.image_lookup[safe_stem(cname)] = str(p)
            dlg.setValue(i + 1)


    def _show_deck_plane(self):
    # Get deck cards however you store them
        deck_name = self._selected_deck_name()
        if not deck_name:
            return
        path = self.deck_files.get(deck_name)
        if not path:
            return
        deck_cards = read_mainboard(path)

        # 1) Pre-fetch all images
        self._ensure_deck_images(deck_cards)

        # 2) Open the plane view
        dlg = DeckPlaneDialog(
            deck_cards=deck_cards,
            image_lookup=self.image_lookup,
            get_card_meta=self._get_card,   # unified cache-backed getter you already have
            parent=self
        )
        dlg.exec_()
