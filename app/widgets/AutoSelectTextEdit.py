from PyQt5.QtWidgets import (
    QLineEdit
)

class AutoSelectTextEdit(QLineEdit):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()