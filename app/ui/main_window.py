from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QComboBox, QPushButton, QLabel, QMessageBox, QSizePolicy, QProgressDialog
)
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt

from app.services.config import AppConfig
from app.services.db import CardDB
from app.services.decks import load_index, read_mainboard
from app.services.images import get_image_lookup, cache_image_for_card, safe_stem
from app.services.search import CardCache, search_in_deck
from app.services.analytics import cmc_from_value
from app.services.visualize import manafy_html
from app.widgets.CardRowWidget import CardRowWidget
from app.widgets.AutoSelectTextEdit import AutoSelectTextEdit
from app.ui.plane_view import DeckPlaneDialog
from app.ui.ImagePopup import ImagePopup, ResultsPopup

from typing import Optional
from string import Template
from pathlib import Path
import matplotlib.pyplot as plt

import os

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTG Deck Analyzer")
        self.setGeometry(100, 100, 1000, 600)

        # Load custom file paths from config.json
        self.config = AppConfig.load()

        # Set up connection to sqlite db for card data lookups
        self.db = CardDB(str(self.config.db_path))

        # Retrieve cached dict with paths to already cached card images
        self.image_lookup = get_image_lookup()
        
        # Load cached card data previously loaded, for quicker retrieval than db lookups
        self.cache = CardCache(self.config.cache_file)
        self.cache.load()

        # Load cockatrice commanders from the data folder and their color identity
        self.deck_files, self.color_ids = load_index(self.config.decks_folder, self.db.lookup_cid)

        # Save the initial list to reset after filtering
        self.deck_files_actu = dict(self.deck_files)

        ### set up UI layout
        main_layout = QHBoxLayout()

        ## Left panel: 
        left_layout = QVBoxLayout()
        
        ###################
        # Filters
        ###################
        
        # Filter all listed decks on cardname or card subtype
        s_layout = QHBoxLayout()

        self.search_dropdown = QComboBox()

        self.search_dropdown.addItems(["Cards", "Subtypes"])
        s_layout.addWidget(self.search_dropdown)

        self.search_input = AutoSelectTextEdit(self)
        self.search_input.setPlaceholderText("Search for a card or subtype")
        self.search_input.returnPressed.connect(self._search_decks)
        s_layout.addWidget(self.search_input)

        btn = QPushButton("Search Decks")
        btn.clicked.connect(self._search_decks)
        s_layout.addWidget(btn)

        left_layout.addLayout(s_layout)

        # Filter all decks on commander's color identity or Reset deck filter
        f_layout = QHBoxLayout()

        self.filter_dropdown = QComboBox()
        self.filter_dropdown.addItems(["Color Identity"])  # extensible
        f_layout.addWidget(self.filter_dropdown)

        self.filter_input = AutoSelectTextEdit(self)
        self.filter_input.setPlaceholderText("Filter for color(s), e.g. wub")
        self.filter_input.returnPressed.connect(self._filter_decks)
        f_layout.addWidget(self.filter_input)

        f_btn = QPushButton("Filter Decks")
        f_btn.clicked.connect(self._filter_decks)
        f_layout.addWidget(f_btn)

        r_btn = QPushButton("Reset Filter")
        r_btn.clicked.connect(self._reset_deck_list)
        f_layout.addWidget(r_btn)

        left_layout.addLayout(f_layout)
        
        ###################
        # Decklist functionalities
        ###################

        # Deck plane view and show mana curve
        df_layout = QHBoxLayout()

        plane_btn = QPushButton("Deck Plane")
        plane_btn.clicked.connect(self._show_deck_plane)
        df_layout.addWidget(plane_btn)

        curve_btn = QPushButton("Mana Curve")
        curve_btn.clicked.connect(self._show_mana_curve)
        df_layout.addWidget(curve_btn)

        gc_btn = QPushButton("List Game Changers")
        gc_btn.clicked.connect(self._count_game_changers)
        df_layout.addWidget(gc_btn)

        left_layout.addLayout(df_layout)
        
        ###################
        # Decklist panel
        ################### 

        # Load with (cached) decklists
        self.deck_list = QListWidget()
        self._init_decklist_items(self.deck_files)
        self.deck_list.itemClicked.connect(self._load_deck_clicked)
        left_layout.addWidget(self.deck_list)

        ###################
        # Cache refresh
        ###################  
       
        bottom_layout = QHBoxLayout()

        # Refresh image cache (walk through image dirs and index all image files, including those newly downloaded)
        refresh_btn = QPushButton("Refresh Img Cache")
        refresh_btn.clicked.connect(self._refresh_image_cache)
        bottom_layout.addWidget(refresh_btn)

        # Refresh decklist cache (read all .cod files, infer commander from their sideboard and look up color identity)
        refresh_decks_btn = QPushButton("Refresh Decklists")
        refresh_decks_btn.clicked.connect(self._refresh_decklists_from_file)
        bottom_layout.addWidget(refresh_decks_btn)

        left_layout.addLayout(bottom_layout)


        main_layout.addLayout(left_layout,stretch=1)

        ## Mid panel: deck contents and commander image
        mid_layout = QVBoxLayout()
        
        # panel to show (small) image of commander(s) for a decklist
        self.general_image_label = QLabel("Commander Image")
        self.general_image_label.setAlignment(Qt.AlignCenter)
        self.general_image_label.setStyleSheet("border: 1px solid black;")
        self.general_image_label.mousePressEvent = self._show_general_image_popup
        mid_layout.addWidget(self.general_image_label, 1)

        # Panel to show cards in the deck, with count and mana value
        self.deck_display = QListWidget()
        self.deck_display.itemClicked.connect(self._show_card_details)
        mid_layout.addWidget(self.deck_display,4)

        main_layout.addLayout(mid_layout,stretch=2)


        ## Right panel: card details

        right_layout = QVBoxLayout()

        # Panel to show selected card image 
        self.card_image_label = QLabel("Card Image")
        self.card_image_label.setAlignment(Qt.AlignCenter)
        self.card_image_label.setStyleSheet("border: 1px solid black;")
        self.card_image_label.mousePressEvent = self._show_image_popup
        right_layout.addWidget(self.card_image_label, 1)

        # Panel to show card details (text)
        self.card_text_display = QLabel("Card Details")
        self.card_text_display.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.card_text_display.setStyleSheet("border: 1px solid black;")
        self.card_text_display.setWordWrap(True)
        self.card_text_display.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_layout.addWidget(self.card_text_display, 1)

        main_layout.addLayout(right_layout,stretch=2)

        # Central widget
        cw = QWidget(); cw.setLayout(main_layout)
        self.setCentralWidget(cw)

        # State (selected card, selected deck)
        self.current_card_image_path = None
        self.current_deck_cards = []

    # ---------- UI helpers ----------
    def _color_hex(self, c: str) -> str:
        """Returns hexcode for an MTG color code, defaulting to dark theme background color."""
        return {"W":"#FFFFFF","U":"#0000FF","B":"#000000","R":"#FF0000","G":"#008000"}.get(c, "#202124")
    
    def _pip_squares(self, identity: str) -> str:
        """Sets up color identity pips in the right order."""
        order = ["W", "U", "B", "R", "G"]
        squares = []
        for c in order:
            active = (c in (identity or ""))
            col = self._color_hex(c) if active else "#3a3a3a"
            squares.append(f'<span style="color:{col}; font-size:14px;">&#9632;</span>')
        return " ".join(squares)
    
    def _get_card(self, card_name: str) -> dict:
        """Looks up card metadata in the cache (as currently loaded), and retrieves it from the database if not found."""
        if not card_name:
            return {}
        data = self.cache.ensure_card(card_name, self.db) or {}
        return data
    
    def _init_decklist_items(self, decks):
        """Initialize or reset the decks panel with the decks provided (in cache, or read from file)."""
        self.deck_list.clear()
        order = ["W","U","B","R","G"]
        # disable auto-update as new ui elements are added while populating the panel
        self.deck_list.setUpdatesEnabled(False)
        try:
            for deck_name in decks:
                identity = self.color_ids.get(deck_name, "")
                squares = " ".join([f'<span style="color:{self._color_hex(c) if c in identity else "#202124"};">&#9632;</span>' for c in order])

                item_widget = QWidget()
                lay = QHBoxLayout()
                lay.setContentsMargins(5,5,5,5)
                color_lbl = QLabel()
                color_lbl.setText(squares)
                color_lbl.setAlignment(Qt.AlignLeft)
                name_lbl = QLabel(deck_name)
                name_lbl.setAlignment(Qt.AlignLeft)
                lay.addWidget(color_lbl)
                lay.addWidget(name_lbl)
                lay.addStretch()
                item_widget.setLayout(lay)

                item = QListWidgetItem(self.deck_list)
                item.setSizeHint(item_widget.sizeHint())
                self.deck_list.addItem(item)
                self.deck_list.setItemWidget(item, item_widget)
        finally:
            self.deck_list.setUpdatesEnabled(True)

    def _selected_deck_name(self):
        """Returns the commander name (i.e. the key) of the currently selected deck."""
        item = self.deck_list.currentItem()
        if not item:
            return None
        return self.deck_list.itemWidget(item).layout().itemAt(1).widget().text().split(" (")[0]

    # ---------- Actions ----------
    def _load_deck_clicked(self, item):
        """Loads the selected deck's content in the mid panel."""
        dn = self.deck_list.itemWidget(item).layout().itemAt(1).widget().text().split(" (")[0]
        self._load_deck_by_name(dn)

    def _load_deck_by_name(self, deck_name: str):
        """Reads a deck's mainboard cards from the xml file and then loads them into the mid panel with display_deck."""
        file_path = self.deck_files.get(deck_name)
        if not file_path:
            return
        self.current_deck_cards = read_mainboard(file_path)

        self._display_deck(self.current_deck_cards)

    def _display_general(self, width, height):
        """Shows the commander(s) as images in the mid panel at the top."""
        general_name = self._selected_deck_name() or ""
        
        # Split names if '&' is present, otherwise create a list with one name
        names = [n.strip() for n in general_name.split('&')] if '&' in general_name else [general_name]
        pixmaps = []
        for name in names:
            img_path = self._get_card_img(name)
            if img_path:
                pix = QPixmap(img_path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pixmaps.append(pix)
        if pixmaps:
            if len(pixmaps) > 1:
                # Calculate dimensions for the combined image
                spacing = 5
                total_width = sum(p.width() for p in pixmaps) + (spacing * (len(pixmaps) - 1))
                max_height = max(p.height() for p in pixmaps)
                
                # Create a transparent canvas
                combined = QPixmap(total_width, max_height)
                combined.fill(Qt.transparent)
                
                # Paint the images side-by-side
                painter = QPainter(combined)
                current_x = 0
                for p in pixmaps:
                    painter.drawPixmap(current_x, 0, p)
                    current_x += p.width() + spacing
                painter.end()
                
                return(combined)
            else:
                # Single image behavior
                return(pixmaps[0])
        else:
            return None
    
    def _display_deck(self, deck_cards):
        """Effectively loads the deck's content into the mid panel and the commander(s) image()s above it."""
        self.deck_display.setUpdatesEnabled(False)
        self.deck_display.clear()
        try:
            general_image = self._display_general(100,150)
            if general_image:
                self.general_image_label.setPixmap(general_image)
            else:
                self.general_image_label.clear(); self.general_image_label.setText("Image not available")
            card_names = [c[0] for c in deck_cards]
            metadata_map = {name: self._get_card(name) for name in card_names}
            for name, qty in deck_cards:
                meta = metadata_map.get(name, {})
                mv = meta.get("manaValue")
                ci = meta.get("colorIdentity") or ""
                row = CardRowWidget(name=name, qty=qty, color_identity=ci, mana_value=mv)
                row.set_pips_html(self._pip_squares(ci))

                item = QListWidgetItem()
                item.setData(Qt.UserRole, name)
                item.setSizeHint(row.sizeHint())
                self.deck_display.addItem(item)
                self.deck_display.setItemWidget(item, row)
        finally:
            self.deck_display.setUpdatesEnabled(True)
            self.cache.save()

    def _search_decks(self):
        """Searches through all decks for a certain query (name or subtype currently supported)."""
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
            results.append(("No results found for query: ",[(query,0)]))
        self._display_search_results(results)

    def _count_game_changers(self):
        """Searches through all decks for a certain query (name or subtype currently supported)."""
        gc_list = self.db.list_game_changers()
        print(gc_list)
        results = []
        for deck_name, path in self.deck_files_actu.items():
            cards = read_mainboard(path)
            matches = search_in_deck(cards, gc_list, self.cache, "Game Changers")
            if matches:
                results.append((deck_name, matches))
        if not results:
            results.append(("No results found for query: ",[("Game Changers",0)]))
        self._display_search_results(results)

    def _display_search_results(self, results):
        """Show search results in a popup."""
        dialog = ResultsPopup(results, "Search Result",self)
        dialog.exec()

    def _reset_deck_list(self):
        """After filtering decks on color identity, reset them."""
        self.deck_files_actu = dict(self.deck_files)
        self._init_decklist_items(self.deck_files)

    def _filter_decks(self):
        """Filter decks on color identity."""
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

    def _get_card_img(self, card_name: str):
        """Returns card image path from image lookup, or go fetch it from scryfall."""
        key = (card_name or "").lower()
        img = self.image_lookup.get(key)
        if not img:
            cached_path = cache_image_for_card(card_name)
            if cached_path:
                # Rebuild lookup so subsequent selections are instant
                self.image_lookup[safe_stem(card_name)] = str(cached_path)
                img = str(cached_path)
        return img
    
    def _show_card_details(self, item):
        """Show card image and details in right panel when clicking a card in a decklist."""
        # Retrieve the card name stored in UserRole (since rows are custom widgets)
        card_name = item.data(Qt.UserRole)
        if not card_name:
            # Fallback: try to parse from text if present
            text = item.text() or ""
            card_name = text.split("x ", 1)[-1].strip()

        # Image
        img = self._get_card_img(card_name)

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
        """Show card image larger in popup when clicking the image."""
        if not self.current_card_image_path:
            return
        pix = QPixmap(self.current_card_image_path)
        popup = ImagePopup(pix, parent=self)
        popup.exec()
        
    def _show_general_image_popup(self, _evt):
        """Show image of the commander(s) in a popup when clicking them."""
        img = self._display_general(460,680)
        if not img:
            return
        popup = ImagePopup(img, parent=self)
        popup.exec()     

    def _ensure_deck_images(self, deck_cards):
        """For plane view, ensure all images are downloaded before showing the view."""
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
        """Show plane view of a deck in a new Dialog."""
        deck_name = self._selected_deck_name()
        if not deck_name:
            QMessageBox.warning(self, "No Deck Selected", "Please select a deck to view its content on the plane.")
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
            get_card_meta=self._get_card,   
            parent=self
        )
        dlg.exec_()
        
    def _show_mana_curve(self):
        """Plot the mana curve of the chosen decklist."""
        deck_name = self._selected_deck_name()
        if not deck_name:
            QMessageBox.warning(self, "No Deck Selected", "Please select a deck to view its mana curve.")
            return
        path = self.deck_files.get(deck_name)
        if not path:
            QMessageBox.warning(self, "Deck Content not found", "Try loading the deck first?")
            return
        deck_cards = self.current_deck_cards
        
        curve: Dict[int, int] = {}
        
        for name, qty in deck_cards:
            meta = self._get_card(name)
            cmc = cmc_from_value(meta.get("manaValue"))
            if cmc is not None:
                curve[cmc] = curve.get(cmc, 0) + qty

        plt.bar(curve.keys(), curve.values())
        plt.title("Mana Curve")
        plt.xlabel("Converted Mana Cost (CMC)")
        plt.ylabel("Number of Cards")
        plt.show()

    def _refresh_image_cache(self):
        """Walk through the image directories to rebuild the image lookup cache."""
        self.image_lookup = get_image_lookup(self.config.image_folder)
        
    def _refresh_decklists_from_file(self):
        """Refresh commanders and their color identity from the .cod files."""
        self.deck_files, self.color_ids = load_index(self.config.decks_folder, self.db.lookup_cid,True)
        self.deck_files_actu = dict(self.deck_files)
        self._init_decklist_items(self.deck_files)