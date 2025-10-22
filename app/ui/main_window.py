from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QComboBox, QLineEdit, QPushButton, QLabel, QMessageBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from app.services.config import AppConfig
from app.services.db import CardDB
from app.services.decks import index_decks_folder, read_mainboard
from app.services.images import build_image_lookup
from app.services.search import CardCache, search_in_deck
from app.services.analytics import mana_curve

from typing import Optional


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

        # Left panel: deck list
        self.deck_list = QListWidget()
        main_layout.addWidget(self.deck_list)
        self._init_decklist_items(self.deck_files)
        self.deck_list.itemClicked.connect(self._load_deck_clicked)

        # Middle panel: search / filters
        mid_layout = QVBoxLayout()

        s_layout = QHBoxLayout()
        self.search_dropdown = QComboBox(); self.search_dropdown.addItems(["Cards", "Subtypes"])
        s_layout.addWidget(self.search_dropdown)
        self.search_input = AutoSelectTextEdit(self); self.search_input.setPlaceholderText("Search for a card or subtype")
        self.search_input.returnPressed.connect(self._search_decks)
        s_layout.addWidget(self.search_input)
        btn = QPushButton("Search Decks"); btn.clicked.connect(self._search_decks)
        s_layout.addWidget(btn)
        mid_layout.addLayout(s_layout)

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
        mid_layout.addLayout(f_layout)

        main_layout.addLayout(mid_layout)

        # Right panel: deck contents + card details
        right_layout = QVBoxLayout()
        self.deck_display = QListWidget(); self.deck_display.itemClicked.connect(self._show_card_details)
        right_layout.addWidget(self.deck_display)

        bottom = QVBoxLayout()
        self.card_image_label = QLabel("Card Image"); self.card_image_label.setAlignment(Qt.AlignCenter)
        self.card_image_label.setStyleSheet("border: 1px solid black;")
        self.card_image_label.mousePressEvent = self._show_image_popup
        bottom.addWidget(self.card_image_label, 2)

        self.card_text_display = QLabel("Card Details"); self.card_text_display.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.card_text_display.setStyleSheet("border: 1px solid black;")
        bottom.addWidget(self.card_text_display, 1)

        right_layout.addLayout(bottom)
        main_layout.addLayout(right_layout)

        # Central widget
        cw = QWidget(); cw.setLayout(main_layout)
        self.setCentralWidget(cw)

        # State
        self.current_card_image_path = None

    # ---------- UI helpers ----------
    def _color_hex(self, c: str) -> str:
        return {"W":"#FFFFFF","U":"#0000FF","B":"#000000","R":"#FF0000","G":"#008000"}.get(c, "#202124")

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
        deck_cards = read_mainboard(file_path)

        # fill cache for missing cards (subtypes, manaValue)
        for cname, _ in deck_cards:
            key = cname.lower()
            if key not in self.cache.cache:
                # try DB by name/faceName
                def fetch():
                    r = self.db.query_one("subtypes, manaValue", "cards", "name = ?", (cname,))
                    if not r:
                        r = self.db.query_one("subtypes, manaValue", "cards", "faceName = ?", (cname,))
                    if r:
                        return {"subtypes": r[0] or "", "manaValue": r[1] or ""}
                    return None
                self.cache.ensure_card(key, fetch)
        self.cache.save()

        self._display_deck(deck_cards)

    def _pip_squares(self, identity: str) -> str:
        order = ["W", "U", "B", "R", "G"]
        squares = []
        for c in order:
            active = (c in (identity or ""))
            col = self._color_hex(c) if active else "#3a3a3a"
            squares.append(f'<span style="color:{col}; font-size:14px;">&#9632;</span>')
        return " ".join(squares)

    def _get_card_meta(self, card_name: str):
        # Query DB for richer metadata, fallback name -> faceName
        res = self.db.query_one(
            "manaValue, type, colorIdentity, text, setCode, power, toughness",
            "cards",
            "name = ?",
            (card_name,)
        )
        if not res:
            res = self.db.query_one(
                "manaValue, type, colorIdentity, text, setCode, power, toughness",
                "cards",
                "faceName = ?",
                (card_name,)
            )
        if not res:
            return {"manaValue": None, "type": "", "colorIdentity": "", "text": "", "setCode": "", "power": "", "toughness": ""}
        keys = ["manaValue", "type", "colorIdentity", "text", "setCode", "power", "toughness"]
        return dict(zip(keys, res))

    def _display_deck(self, deck_cards):
        self.deck_display.clear()
        for name, qty in deck_cards:
            meta = self._get_card_meta(name)
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
        if img:
            self.card_image_label.setPixmap(QPixmap(img).scaled(200, 300, Qt.KeepAspectRatio, transformMode=Qt.SmoothTransformation))
            self.current_card_image_path = img
        else:
            self.card_image_label.clear(); self.card_image_label.setText("Image not available")

        # Metadata
        meta = self._get_card_meta(card_name)
        mv = meta.get("manaValue")
        mv_txt = str(int(float(mv))) if (mv not in (None, "")) else "—"
        type_line = meta.get("type") or ""
        oracle = meta.get("text") or ""
        set_code = meta.get("setCode") or ""
        power = meta.get("power") or ""
        toughness = meta.get("toughness") or ""
        ci = meta.get("colorIdentity") or ""

        html = f"""
        <div style='font-size:14px;'>
          <div style='font-size:16px; font-weight:700; margin-bottom:4px;'>{card_name}</div>
          <div>{self._pip_squares(ci)}
               <span style='margin-left:8px; padding:2px 8px; border-radius:10px; background:#2a2a2a; color:#eee;'>MV {mv_txt}</span>
               <span style='margin-left:8px; color:#999;'>[{set_code}</span>
          </div>
          <div style='margin-top:6px; color:#ccc;'><i>{type_line}</i></div>
            <div style='margin-top:8px; color:#ddd; white-space:normal; word-wrap:break-word; overflow-wrap:break-word;'>
               {oracle}
            </div>
          {f"<div style='margin-top:6px; color:#ccc;'><i>Power: {power}</i></div>" if power else ""}
          {f"<div style='margin-top:4px; color:#ccc;'><i>Toughness: {toughness}</i></div>" if toughness else ""}
        </div>
        """
        self.card_text_display.setText(html)

    def _show_image_popup(self, _evt):
        if not self.current_card_image_path:
            return
        popup = QMessageBox(); popup.setWindowTitle("Card Image")
        pix = QPixmap(self.current_card_image_path)
        popup.setIconPixmap(pix.scaled(400, 600, Qt.KeepAspectRatio))
        popup.exec()