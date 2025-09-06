# ui/dialogs.py
from PyQt6.QtWidgets import QMessageBox

def confirm_param_change(param_name: str, value: str) -> bool:
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("Confirm Parameter Change")
    msg.setText(f"Are you sure you want to set <b>{param_name}</b> to <b>{value}</b>?")
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    result = msg.exec()
    return result == QMessageBox.StandardButton.Yes
