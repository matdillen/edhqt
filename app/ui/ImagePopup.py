from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
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