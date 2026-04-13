from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QTextBrowser, QMessageBox
from PyQt5.QtCore import Qt, QUrl
from urllib.parse import unquote

from app.services.analytics import get_stat_help_text

class ImagePopup(QDialog):
    def __init__(self, pixmaps, title="Card Preview", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        
        # Main Layout (Vertical)
        layout = QVBoxLayout(self)
        
        # Image Layout (Horizontal)
        img_layout = QHBoxLayout()
        lbl = QLabel()
        # Scale slightly larger for the popup if you like
        lbl.setPixmap(pixmaps.scaled(460, 680, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        img_layout.addWidget(lbl)
        
        layout.addLayout(img_layout)
        
        # Add a close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        # This ensures the window shrinks/grows to fit the content exactly
        self.layout().setSizeConstraint(QVBoxLayout.SetFixedSize)

class ResultsPopup(QDialog):
    def __init__(self, results: list, title="Card Preview", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        
        # Main Layout (Vertical)
        layout = QVBoxLayout(self)
        
        # Using QTextEdit for better formatting and copy-pasting
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        layout.addWidget(self.text_display)
        
        self._format_results(results)
        
        # Add a close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _format_results(self, results):
        formatted_text = ""
        for deck_name, cards in results:
            formatted_text += f"Deck: {deck_name}\n"
            for card_name, qty in cards:
                formatted_text += f"    {qty}x {card_name}\n"
            formatted_text += "\n"  # Spacing between decks
        
        self.text_display.setPlainText(formatted_text)


class StatsPopup(QDialog):
    def __init__(self, html: str, title="Deck Stats", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(920, 700)

        layout = QVBoxLayout(self)

        self.html_display = QTextBrowser()
        self.html_display.setReadOnly(True)
        self.html_display.setOpenLinks(False)
        self.html_display.anchorClicked.connect(self._handle_anchor_clicked)
        self.html_display.setHtml(html)
        layout.addWidget(self.html_display)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _handle_anchor_clicked(self, url: QUrl):
        if url.scheme() != "stat":
            return
        label = unquote(url.path().lstrip("/") or url.host() or url.toString()[5:])
        help_text = get_stat_help_text(label)
        if help_text:
            QMessageBox.information(self, label, help_text)
