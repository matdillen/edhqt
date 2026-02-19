from PyQt5.QtWidgets import QApplication
import sys
import qdarkstyle
from app.ui.main_window import MainWindow

def run():
    app = QApplication(sys.argv)
    # Optional theme
    dark_stylesheet = qdarkstyle.load_stylesheet_pyqt5()
    app.setStyleSheet(dark_stylesheet)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()