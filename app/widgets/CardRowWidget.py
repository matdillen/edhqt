from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt
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