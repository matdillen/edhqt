import sys
import os
import sqlite3
import requests
import json
import csv
import xml.etree.ElementTree as ET
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QListWidget, QLineEdit, QPushButton, QLabel, QWidget, QTableWidget, QTableWidgetItem, QMessageBox, QComboBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class MTGDeckAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Load configuration
        with open("config.json", "r") as config_file:
            config = json.load(config_file)

        self.decks_folder = config.get("decks_folder", "./decks")
        self.db_path = config.get("db_path", "./allprintings.sqlite")
        self.image_folder = config.get("image_folder", "./images")
        self.cache_file = config.get("cache_file", "./card_cache.csv")

        self.setWindowTitle("MTG Deck Analyzer")
        self.setGeometry(100, 100, 1000, 600)

        self.db_connection = self.connect_to_db(self.db_path)
        self.image_lookup = self.build_image_lookup()  # Pre-build image lookup table
        self.deck_files = self.index_decks_folder()  # Index the decks folder
        self.card_cache = self.load_card_cache()  # Load card cache

        # Main Layout
        main_layout = QHBoxLayout()

        # Left Panel: Deck List and Search
        left_layout = QVBoxLayout()

        self.deck_list = QListWidget()
        self.deck_list.addItems(self.deck_files.keys())
        self.deck_list.itemClicked.connect(self.load_deck)
        left_layout.addWidget(self.deck_list)

        search_layout = QHBoxLayout()
        self.search_dropdown = QComboBox()
        self.search_dropdown.addItems(["Cards", "Subtypes"])
        search_layout.addWidget(self.search_dropdown)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for a card or subtype")
        self.search_input.returnPressed.connect(self.search_decks)
        search_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("Search Decks")
        self.search_button.clicked.connect(self.search_decks)
        search_layout.addWidget(self.search_button)
        left_layout.addLayout(search_layout)

        self.reset_button = QPushButton("Reset Search")
        self.reset_button.clicked.connect(self.reset_deck_list)
        left_layout.addWidget(self.reset_button)

        self.mana_curve_button = QPushButton("Show Mana Curve")
        self.mana_curve_button.clicked.connect(self.show_mana_curve)
        left_layout.addWidget(self.mana_curve_button)

        main_layout.addLayout(left_layout)

        # Top Right Panel: Deck Contents
        right_layout = QVBoxLayout()

        self.deck_display = QListWidget()
        self.deck_display.itemClicked.connect(self.show_card_details)
        right_layout.addWidget(self.deck_display)

        # Bottom Right Panel: Card Details
        bottom_layout = QVBoxLayout()

        self.card_image_label = QLabel("Card Image")
        self.card_image_label.setAlignment(Qt.AlignCenter)
        self.card_image_label.setStyleSheet("border: 1px solid black;")
        self.card_image_label.mousePressEvent = self.show_image_popup
        bottom_layout.addWidget(self.card_image_label, 2)

        self.card_text_display = QLabel("Card Details")
        self.card_text_display.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.card_text_display.setStyleSheet("border: 1px solid black;")
        bottom_layout.addWidget(self.card_text_display, 1)

        right_layout.addLayout(bottom_layout)
        main_layout.addLayout(right_layout)

        # Set central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.currently_displayed_image = None  # Track the currently displayed image to prevent duplicate logs
        self.current_card_image_path = None

    def build_image_lookup(self):
        logging.info("Building image lookup table.")
        image_lookup = {}

        for root, dirs, files in os.walk(self.image_folder):
            for file in files:
                if file.endswith(".jpg"):
                    card_name = os.path.splitext(file)[0]
                    image_lookup[card_name.lower()] = os.path.join(root, file)

        logging.info(f"Image lookup table built with {len(image_lookup)} entries.")
        return image_lookup

    def connect_to_db(self, db_path):
        try:
            connection = sqlite3.connect(db_path)
            logging.info(f"Connected to database at {db_path}")
            return connection
        except sqlite3.Error as e:
            logging.error(f"Database connection failed: {e}")
            return None

    def index_decks_folder(self):
        logging.info("Indexing decks folder.")
        deck_files = {}

        for file in os.listdir(self.decks_folder):
            if file.endswith(".cod"):
                deck_files[file] = os.path.join(self.decks_folder, file)

        logging.info(f"Indexed {len(deck_files)} deck files.")
        return deck_files

    def load_card_cache(self):
        card_cache = {}
        if os.path.exists(self.cache_file):
            logging.info("Loading card cache from file.")
            with open(self.cache_file, "r") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    card_cache[row["name"].lower()] = {
                        "subtypes": row["subtypes"],
                        "manaValue": row["manaValue"]
                    }
        else:
            logging.info("Card cache file not found, it will be created during deck loading.")
        return card_cache

    def save_card_cache(self):
        logging.info("Saving card cache to file.")
        with open(self.cache_file, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["name", "subtypes", "manaValue"])
            writer.writeheader()
            for name, data in self.card_cache.items():
                writer.writerow({"name": name, "subtypes": data["subtypes"], "manaValue": data.get("manaValue", "")})

    def load_deck(self, item):
        deck_file = self.deck_files[item.text()]

        try:
            tree = ET.parse(deck_file)
            root = tree.getroot()

            deck_data = []
            self.deck_display.clear()

            for card in root.findall("./zone[@name='main']/card"):
                card_name = card.attrib['name']
                quantity = int(card.attrib['number'])

                if card_name.lower() not in self.card_cache:
                    cursor = self.db_connection.cursor()
                    cursor.execute("SELECT subtypes, manaValue FROM cards WHERE name = ?", (card_name,))
                    result = cursor.fetchone()
                    if result:
                        self.card_cache[card_name.lower()] = {
                            "subtypes": result[0],
                            "manaValue": result[1]
                        }

                deck_data.append((card_name, quantity))

            self.save_card_cache()
            self.display_deck_data(deck_data)
        except Exception as e:
            logging.error(f"Error loading deck {deck_file}: {e}")

    def display_deck_data(self, deck_data):
        self.deck_display.clear()

        for card_name, quantity in deck_data:
            self.deck_display.addItem(f"{quantity}x {card_name}")

    def calculate_mana_curve(self, deck_data):
        mana_curve = {}

        for card_name, quantity in deck_data:
            card_data = self.card_cache.get(card_name.lower())
            if card_data:
                manaValue = card_data.get("manaValue", "")
                cmc = self.get_cmc_from_manaValue(manaValue)
                if cmc is not None:
                    mana_curve[cmc] = mana_curve.get(cmc, 0) + quantity

        return mana_curve

    def get_cmc_from_manaValue(self, manaValue):
        try:
            if manaValue is None:
                return None
            return int(float(manaValue))
        except Exception as e:
            logging.error(f"Error calculating CMC from mana cost {manaValue}: {e}")
            return None

    def show_mana_curve(self):
        try:
            selected_deck = self.deck_list.currentItem()
            if not selected_deck:
                QMessageBox.warning(self, "No Deck Selected", "Please select a deck to view its mana curve.")
                return

            deck_file = self.deck_files[selected_deck.text()]
            tree = ET.parse(deck_file)
            root = tree.getroot()

            deck_data = []
            for card in root.findall("./zone[@name='main']/card"):
                card_name = card.attrib['name']
                quantity = int(card.attrib['number'])
                deck_data.append((card_name, quantity))

            mana_curve = self.calculate_mana_curve(deck_data)

            if mana_curve:
                plt.bar(mana_curve.keys(), mana_curve.values())
                plt.title("Mana Curve")
                plt.xlabel("Converted Mana Cost (CMC)")
                plt.ylabel("Number of Cards")
                plt.show()
            else:
                QMessageBox.information(self, "Empty Mana Curve", "This deck has no cards with a valid mana cost.")
        except Exception as e:
            logging.error(f"Error showing mana curve: {e}")

    def search_decks(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        search_type = self.search_dropdown.currentText()
        matching_decks = []

        for deck_name, deck_path in self.deck_files.items():
            try:
                tree = ET.parse(deck_path)
                root = tree.getroot()
                deck_matches = []

                for card in root.findall("./zone[@name='main']/card"):
                    card_name = card.attrib['name']
                    quantity = int(card.attrib['number'])

                    if search_type == "Cards":
                        if query in card_name.lower():
                            deck_matches.append((card_name, quantity))
                    elif search_type == "Subtypes":
                        card_data = self.card_cache.get(card_name.lower())
                        if card_data and any(q.strip() in card_data["subtypes"].lower() for q in query.split(',')):
                            deck_matches.append((card_name, quantity))

                if deck_matches:
                    matching_decks.append((deck_name, deck_matches))
            except Exception as e:
                logging.error(f"Error searching deck {deck_path}: {e}")

        self.display_search_results(matching_decks)

    def display_search_results(self, matching_decks):
        self.deck_display.clear()

        for deck_name, cards in matching_decks:
            self.deck_display.addItem(f"Deck: {deck_name}")
            for card_name, quantity in cards:
                self.deck_display.addItem(f"    {quantity}x {card_name}")

    def reset_deck_list(self):
        self.deck_list.clear()
        self.deck_list.addItems(self.deck_files.keys())

    def show_card_details(self, item):
        card_name = item.text().split("x ", 1)[-1].strip()
        card_name_key = card_name.lower()
        
        if card_name_key in self.image_lookup:
            image_path = self.image_lookup[card_name_key]
            self.card_image_label.setPixmap(QPixmap(image_path).scaled(200, 300, Qt.KeepAspectRatio))
            self.current_card_image_path = image_path
        else:
            self.card_image_label.clear()
            self.card_image_label.setText("Image not available")

        self.card_text_display.setText(f"Card Name: {card_name}")

    def show_image_popup(self, event):
        if self.current_card_image_path:
            popup = QMessageBox()
            popup.setWindowTitle("Card Image")
            pixmap = QPixmap(self.current_card_image_path)
            popup.setIconPixmap(pixmap.scaled(400, 600, Qt.KeepAspectRatio))
            popup.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MTGDeckAnalyzer()
    window.show()
    sys.exit(app.exec_())
