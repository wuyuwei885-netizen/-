APP_STYLE = """
QMainWindow, QWidget {
    background: #F8FAFC;
    color: #0F172A;
    font-family: "Microsoft YaHei", "Segoe UI", Arial;
}
QPushButton {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px 12px;
    background: #FFFFFF;
    color: #334155;
}
QPushButton:hover {
    background: #F1F5F9;
}
QPushButton#primaryButton {
    background: #2563EB;
    color: white;
    border-color: #2563EB;
}
QPushButton#primaryButton:hover {
    background: #1D4ED8;
}
QPushButton#navButton {
    text-align: left;
    border: 0;
    padding: 10px 12px;
}
QPushButton#navButton[active="true"] {
    background: #EFF6FF;
    color: #1D4ED8;
}
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 7px;
}
QTableWidget {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    gridline-color: #E2E8F0;
}
QHeaderView::section {
    background: #F8FAFC;
    border: 0;
    border-bottom: 1px solid #E2E8F0;
    padding: 8px;
    color: #475569;
}
QListWidget {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}
"""
