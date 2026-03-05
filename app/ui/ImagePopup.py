from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
from PyQt5.QtCore import Qt

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