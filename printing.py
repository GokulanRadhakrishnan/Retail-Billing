import sys
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QDialog, QApplication, QMessageBox
)
from PyQt5.QtPrintSupport import QPrintDialog, QPrintPreviewDialog
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PyQt5.QtGui import QTextCursor, QFont, QFontMetrics
from PyQt5.QtCore import Qt

class PrintPreviewDialog(QDialog):
    """
    PyQt5 dialog for print preview & send to 58mm thermal printer.
    Use with data from sales module or bill generator.
    """
    def __init__(self, bill_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Print Preview (58mm Thermal Format)")
        self.resize(400, 600)
        self.bill_text = bill_text
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        font = QFont("Consolas", 9)
        self.text_edit = QTextEdit()
        self.text_edit.setFont(font)
        self.text_edit.setReadOnly(True)
        self.text_edit.setText(self.bill_text)
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()
        btn_print = QPushButton("Print")
        btn_print.clicked.connect(self.handle_print)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def handle_print(self):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.Custom)
        # 58mm width: about 165 pixels at 200dpi; set page size accordingly
        printer.setPaperSize(QPrinter.Inch)
        printer.setPageMargins(2, 2, 2, 2, QPrinter.Millimeter)
        printer.setPrinterName("")  # Default printer
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() == QPrintDialog.Accepted:
            self.text_edit.print_(printer)
            QMessageBox.information(self, "Printed", "Sent to printer.")

def pretty_bill_text(shop_name, shop_phone, bill_no, date, customer, mobile, products, subtotal, discount, gst_total, total):
    """
    Create fixed-width thermal (58mm) receipt format.
    products: list of dicts with keys "Product Name", "Quantity", "Sale Price"
    """
    lines = []
    lines.append(f"{shop_name:^32}")
    lines.append(f"Ph: {shop_phone:^25}")
    lines.append(f"Bill No:{bill_no:<6}  Date:{date:<10}")
    lines.append("-"*32)
    lines.append(f"Customer: {customer[:17]:<17}")
    lines.append(f"Mobile: {mobile:>14}")
    lines.append("-"*32)
    lines.append(f"{'Product':<12}{'Qty':>5}{'Pr':>7}")
    for p in products:
        pname = str(p["Product Name"])[:12]
        qty = f"{p['Quantity']:>4}"
        price = f"{p['Sale Price']:>7.2f}"
        lines.append(f"{pname:<12}{qty:>5}{price:>7}")
    lines.append("-"*32)
    lines.append(f"Subtotal: ₹{subtotal:>8.2f}")
    lines.append(f"Discount: ₹{discount:>8.2f}")
    lines.append(f"GST:      ₹{gst_total:>8.2f}")
    lines.append(f"Total:    ₹{total:>8.2f}")
    lines.append("-"*32)
    lines.append("Thank you! Visit again.")
    return "\n".join(lines)

def show_bill_print_preview(
    shop_name, shop_phone, bill_no, date, customer, mobile,
    products, subtotal, discount, gst_total, total, parent=None
):
    """
    Display modal print preview window for the given sale data.
    """
    bill_str = pretty_bill_text(
        shop_name, shop_phone, bill_no, date, customer, mobile,
        products, subtotal, discount, gst_total, total
    )
    dlg = PrintPreviewDialog(bill_str, parent)
    dlg.exec_()

# Example usage:
if __name__ == "__main__":
    app = QApplication(sys.argv)
    sample_products = [
        {"Product Name": "Urea 45kg", "Quantity": 2, "Sale Price": 650.00},
        {"Product Name": "Seed Pack", "Quantity": 1, "Sale Price": 120.00},
    ]
    show_bill_print_preview(
        shop_name="Sri Krishna Agro Centre",
        shop_phone="6383958656",
        bill_no=41,
        date="22-07-2025",
        customer="R. Kumar",
        mobile="9876501234",
        products=sample_products,
        subtotal=1420.00,
        discount=20.00,
        gst_total=32.50,
        total=1432.50
    )
    sys.exit(app.exec_())
