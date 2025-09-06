import sys, os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QDialog, QApplication, QMessageBox
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrinterInfo
from PyQt5.QtGui import QTextCursor, QFont, QFontMetrics
from PyQt5.QtCore import Qt, QSizeF
from datetime import datetime

# Optional Windows raw printing via pywin32
try:
    import win32print, win32ui, win32con
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False

def _select_native_printer(printer: QPrinter) -> bool:
    """
    Try to bind QPrinter to a native installed printer.
    Returns True if a native printer was selected, else False.
    """
    try:
        printers = QPrinterInfo.availablePrinters()
        if not printers:
            return False
        # Prefer system default, else pick first available
        default_info = QPrinterInfo.defaultPrinter()
        chosen = default_info if default_info and not default_info.isNull() else printers[0]
        printer.setOutputFormat(QPrinter.NativeFormat)
        printer.setPrinterName(chosen.printerName())
        return True
    except Exception:
        return False

# Direct Windows raw printing using GDI (pywin32)
# Mirrors the settings you provided (Courier New, MM_TWIPS, line spacing).

def print_bill_win32(bill_text: str):
    if not HAS_WIN32:
        raise RuntimeError("pywin32 not available")
    printer_name = win32print.GetDefaultPrinter()
    if not printer_name:
        raise RuntimeError("No default printer configured")

    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(hPrinter, 1, ("Your company Bill", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)

        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)

        hDC.SetMapMode(win32con.MM_TWIPS)
        hDC.StartDoc("Your company Bill")
        hDC.StartPage()

        font = win32ui.CreateFont({
            "name": "Courier New",
            "height": -150,  # ~10.5pt
            "weight": 500
        })
        hDC.SelectObject(font)
        x = 100
        y = -100
        for line in bill_text.split("\n"):
            hDC.TextOut(x, y, line)
            y -= 200  # line spacing

        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()

        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)

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
        # Try Windows raw printing first (no dialog), matching your settings
        if 'HAS_WIN32' in globals() and HAS_WIN32:
            try:
                print_bill_win32(self.text_edit.toPlainText())
                QMessageBox.information(self, "Printed", "Sent to printer.")
                return
            except Exception:
                # Fall through to Qt printing
                pass
        printer = QPrinter(QPrinter.HighResolution)
        # Configure paper size for 58mm thermal
        try:
            printer.setPageSize(QPrinter.Custom)
            printer.setPaperSize(QSizeF(58, 200), QPrinter.Millimeter)
        except Exception:
            printer.setPageSize(QPrinter.A6)
        printer.setPageMargins(2, 2, 2, 2, QPrinter.Millimeter)

        # Try native print dialog by binding to an installed printer; fallback to PDF if none
        try:
            if _select_native_printer(printer):
                dialog = QPrintDialog(printer, self)
                if dialog.exec_() == QPrintDialog.Accepted:
                    self.text_edit.print_(printer)
                    QMessageBox.information(self, "Printed", "Sent to printer.")
                    return
                else:
                    # User canceled dialog; stop silently
                    return
            # No native printers available -> PDF fallback
            raise RuntimeError("No native printer available")
        except Exception:
            # Save as PDF in data/prints
            try:
                out_dir = os.path.join("data", "prints")
                os.makedirs(out_dir, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = os.path.join(out_dir, f"receipt_{ts}.pdf")
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(out_path)
                self.text_edit.print_(printer)
                QMessageBox.information(self, "Saved PDF", f"No native printer. Receipt saved to:\n{out_path}")
            except Exception as e:
                QMessageBox.critical(self, "Print Error", f"Unable to print or save PDF.\n{e}")

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
        shop_name="Gokulan's Pharma",
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
