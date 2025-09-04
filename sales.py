import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QCompleter, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QStringListModel
from openpyxl import Workbook, load_workbook
from datetime import datetime, timedelta
import sqlite3
from purchases import carry_forward_purchase_fy_stock, purchase_excel_path, get_product_category_from_db
from utils import update_customer_data_file, ensure_customer_data_file, add_or_update_customer, CUSTOMER_DATA_FILE
from PyQt5.QtGui import QRegularExpressionValidator
from PyQt5.QtCore import QRegularExpression

SALES_FILE_DIR = "data"
PAYMENT_MODES = ["Cash", "UPI", "Both"]

CUSTOMER_DATA_FILE = "data/customer_data.xlsx"
SQLITE_DB_PATH = "data/sales_data.db"


def ensure_customer_data_file():
    if not os.path.exists(CUSTOMER_DATA_FILE):
        wb = Workbook()
        ws_cust = wb.active
        ws_cust.title = "Customers"
        ws_cust.append(["Customer Name", "Mobile", "Village", "Aadhar", "Entry By", "Created At"])
        ws_ph = wb.create_sheet("PurchaseHistory")
        ws_ph.append([
            "Bill Number", "Date", "Mobile", "Products", "Subtotal", "Discount", "GST Total", "Total",
            "Payment Mode", "Cash Amount", "UPI Amount", "Entry By"
        ])
        wb.save(CUSTOMER_DATA_FILE)


def financial_year_for_date(date: QDate):
    month = date.month()
    year = date.year()
    return f"{year}-{year+1}" if month >= 4 else f"{year-1}-{year}"


def sales_excel_path_month(date: QDate):
    fname = f"Sales_{date.toString('yyyy-MM')}.xlsx"
    return os.path.join(SALES_FILE_DIR, fname)


def sales_excel_path_fy(date: QDate):
    fy = financial_year_for_date(date)
    fname = f"Sales_FY_{fy}.xlsx"
    return os.path.join(SALES_FILE_DIR, fname)


def ensure_sqlite_db():
    os.makedirs(SALES_FILE_DIR, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            bill_number INTEGER PRIMARY KEY,
            date TEXT,
            customer_name TEXT,
            mobile TEXT,
            village TEXT,
            aadhar TEXT,
            product_details TEXT,
            subtotal REAL,
            discount REAL,
            gst_total REAL,
            total REAL,
            payment_mode TEXT,
            cash_amount REAL,
            upi_amount REAL,
            entry_by TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            mobile TEXT PRIMARY KEY,
            customer_name TEXT,
            village TEXT,
            aadhar TEXT,
            entry_by TEXT,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS purchase_stock (
            product_name TEXT PRIMARY KEY,
            quantity REAL
        )
    ''')
    conn.commit()
    conn.close()


def get_last_bill_number_from_db():
    ensure_sqlite_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(bill_number) FROM bills")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else 0


def insert_bill_into_db(bill_data):
    ensure_sqlite_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO bills (
                bill_number, date, customer_name, mobile, village, aadhar,
                product_details, subtotal, discount, gst_total, total,
                payment_mode, cash_amount, upi_amount, entry_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', bill_data)
        conn.commit()
    except sqlite3.IntegrityError:
        c.execute('''
            UPDATE bills SET
            date=?, customer_name=?, mobile=?, village=?, aadhar=?, product_details=?,
            subtotal=?, discount=?, gst_total=?, total=?, payment_mode=?,
            cash_amount=?, upi_amount=?, entry_by=?
            WHERE bill_number=?
        ''', bill_data[1:] + (bill_data[0],))
        conn.commit()
    finally:
        conn.close()


def insert_or_update_customer_in_db(cust_info):
    ensure_sqlite_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT mobile FROM customers WHERE mobile = ?', (cust_info['mobile'],))
    exists = c.fetchone()
    if exists:
        c.execute('''
            UPDATE customers SET
            customer_name=?, village=?, aadhar=?, entry_by=?, created_at=?
            WHERE mobile=?
        ''', (
            cust_info['cust_name'], cust_info['village'], cust_info['aadhar'],
            cust_info['entry_by'], cust_info['created_at'], cust_info['mobile']
        ))
    else:
        c.execute('''
            INSERT INTO customers (
                mobile, customer_name, village, aadhar, entry_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            cust_info['mobile'], cust_info['cust_name'], cust_info['village'],
            cust_info['aadhar'], cust_info['entry_by'], cust_info['created_at']
        ))
    conn.commit()
    conn.close()


def reduce_stock_in_db(products):
    """
    Reduce purchase_stock quantities in DB based on products sold.
    products: list of dict with keys 'Product Name' and 'Quantity'
    """
    ensure_sqlite_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    try:
        for p in products:
            c.execute("SELECT quantity FROM purchase_stock WHERE product_name=?", (p["Product Name"],))
            row = c.fetchone()
            if row:
                new_qty = max(0, row[0] - p["Quantity"])
                c.execute("UPDATE purchase_stock SET quantity=? WHERE product_name=?", (new_qty, p["Product Name"]))
        conn.commit()
    except Exception as e:
        print(f"Stock reduction error: {e}")
    finally:
        conn.close()


class SalesWidget(QWidget):
    def __init__(self, auth_manager=None, purchase_excel_path_func=None, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.purchase_excel_path_func = purchase_excel_path_func
        self.current_products = []
        self.last_bill_no = 0
        self.customer_cache = {}

        self.excel_path_month = sales_excel_path_month(QDate.currentDate())
        self.excel_path_fy = sales_excel_path_fy(QDate.currentDate())
        self.ensure_excel_structure(self.excel_path_month)
        self.ensure_excel_structure(self.excel_path_fy)

        if self.purchase_excel_path_func:
            carry_forward_purchase_fy_stock(QDate.currentDate(), self.purchase_excel_path_func)

        self.last_bill_no = get_last_bill_number_from_db()

        self.init_ui()
        self.load_purchase_products()
        self.load_customer_cache()

    def ensure_excel_structure(self, path):
        os.makedirs(SALES_FILE_DIR, exist_ok=True)
        if not os.path.exists(path):
            wb = Workbook()
            ws = wb.active
            ws.title = "Bills"
            ws.append([
                "Bill Number", "Date", "Customer Name", "Mobile", "Village", "Aadhar",
                "Product Details", "Subtotal", "Discount", "GST Total", "Total",
                "Payment Mode", "Cash Amount", "UPI Amount", "Entry By"
            ])
            ws_cust = wb.create_sheet("CustomerWise")
            ws_cust.append(["Customer Name", "Mobile", "Village", "Aadhar", "Entry By"])
            ws_prod = wb.create_sheet("ProductWise")
            ws_prod.append(["Product Name", "Quantity Sold", "Sale Price", "Bill No", "Date", "Entry By"])
            ws_cat = wb.create_sheet("CategoryWise")
            ws_cat.append([
                "Bill Number", "Date", "Customer Name", "Mobile", "Product Name",
                "Quantity", "Sale Price", "Category", "Entry By"
            ])
            wb.save(path)

    def init_ui(self):
        self.setLayout(QVBoxLayout())

        # --- Customer Details ---
        cust_layout = QHBoxLayout()

        self.cust_name = QLineEdit()
        self.cust_name.setPlaceholderText("Customer Name")
        self.cust_mobile = QLineEdit()
        self.cust_mobile.setPlaceholderText("Mobile Number")
        self.cust_village = QLineEdit()
        self.cust_village.setPlaceholderText("Village")
        self.cust_aadhar = QLineEdit()
        self.cust_aadhar.setPlaceholderText("Aadhar")

        # On mobile input Enter, fetch customer details
        self.cust_mobile.returnPressed.connect(self.fetch_customer_by_mobile)
        self.cust_name.returnPressed.connect(lambda: self.cust_village.setFocus())
        self.cust_village.returnPressed.connect(lambda: self.cust_aadhar.setFocus())
        self.cust_aadhar.returnPressed.connect(lambda: self.product_name_input.setFocus())

        cust_layout.addWidget(QLabel("Name:"))
        cust_layout.addWidget(self.cust_name)
        cust_layout.addWidget(QLabel("Mobile:"))
        cust_layout.addWidget(self.cust_mobile)
        cust_layout.addWidget(QLabel("Village:"))
        cust_layout.addWidget(self.cust_village)
        cust_layout.addWidget(QLabel("Aadhar:"))
        cust_layout.addWidget(self.cust_aadhar)

        self.layout().addLayout(cust_layout)

        # --- Product Entry ---
        prod_entry_layout = QHBoxLayout()

        self.product_name_input = QLineEdit()
        self.product_name_input.setPlaceholderText("Product Name")
        self.product_qty_input = QLineEdit()
        self.product_qty_input.setPlaceholderText("Quantity")
        self.product_price_input = QLineEdit()
        self.product_price_input.setPlaceholderText("Sale Price")

        # Setup product autocomplete
        self.product_completer = QCompleter()
        self.product_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.product_name_input.setCompleter(self.product_completer)

        # On product name enter move focus to qty
        self.product_name_input.returnPressed.connect(lambda: self.product_qty_input.setFocus())
        self.product_qty_input.returnPressed.connect(lambda: self.product_price_input.setFocus())
        self.product_price_input.returnPressed.connect(self.add_product_to_list)

        prod_entry_layout.addWidget(QLabel("Product:"))
        prod_entry_layout.addWidget(self.product_name_input)
        prod_entry_layout.addWidget(QLabel("Qty:"))
        prod_entry_layout.addWidget(self.product_qty_input)
        prod_entry_layout.addWidget(QLabel("Price:"))
        prod_entry_layout.addWidget(self.product_price_input)

        self.layout().addLayout(prod_entry_layout)

        # --- Products Table ---
        self.products_table = QTableWidget(0, 4)
        self.products_table.setHorizontalHeaderLabels(["Product Name", "Quantity", "Sale Price", "Amount"])
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout().addWidget(self.products_table)

        # --- Discount and Payment ---
        discount_layout = QHBoxLayout()
        discount_layout.addWidget(QLabel("Discount:"))
        self.discount_input = QLineEdit("0")
        discount_layout.addWidget(self.discount_input)

        discount_layout.addWidget(QLabel("Payment Mode:"))
        self.payment_mode_combo = QComboBox()
        self.payment_mode_combo.addItems(PAYMENT_MODES)
        discount_layout.addWidget(self.payment_mode_combo)

        discount_layout.addWidget(QLabel("Cash Amount:"))
        self.cash_amount_input = QLineEdit("0")
        discount_layout.addWidget(self.cash_amount_input)

        discount_layout.addWidget(QLabel("UPI Amount:"))
        self.upi_amount_input = QLineEdit("0")
        discount_layout.addWidget(self.upi_amount_input)

        self.layout().addLayout(discount_layout)

        # On payment mode change autofill amounts
        self.payment_mode_combo.currentTextChanged.connect(self.autofill_payment_amounts)

        # --- Total display ---
        total_layout = QHBoxLayout()
        total_layout.addStretch()
        self.total_label = QLabel("Total: ₹0.00")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 18px; color: green;")
        total_layout.addWidget(self.total_label)
        self.layout().addLayout(total_layout)

        # --- Save Button ---
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save & Print Bill")
        self.save_btn.clicked.connect(self.save_and_print_bill)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        self.layout().addLayout(btn_layout)

    def load_purchase_products(self):
        products = set()
        try:
            import sqlite3
            # Use the same DB file that purchases.py writes to. Unify this path in a config.
            DB_FILE = "purchases.db"  # or os.path.join("data", "purchase_data.db")
            if os.path.exists(DB_FILE):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT DISTINCT product_name FROM purchases")
                for (pname,) in c.fetchall():
                    if pname:
                       products.add(str(pname).strip())
                conn.close()
        except Exception as e:
           print(f"Failed to load products from DB: {e}")

        # Fallback to Excel if DB is empty or unavailable
        if not products and self.purchase_excel_path_func:
           try:
              path = self.purchase_excel_path_func(QDate.currentDate())
              if os.path.exists(path):
                 wb = load_workbook(path, read_only=True, data_only=True)
                 ws = wb["Invoices"] if "Invoices" in wb.sheetnames else wb[wb.sheetnames[0]]
                 for row in ws.iter_rows(min_row=2, values_only=True):
                     product_name = row[3] if len(row) > 3 else None
                     if product_name:
                         products.add(str(product_name).strip())
                 wb.close()
           except Exception as e:
              print(f"Failed to load purchase products from Excel: {e}")

        self.purchase_products_cache = sorted(products)
        model = QStringListModel(self.purchase_products_cache)
        self.product_completer.setModel(model)

    def _normalize_mobile(self, s: str) -> str:
        return ''.join(ch for ch in s if ch.isdigit())

    def load_customer_cache(self):
        self.customer_cache.clear()
        # Load customers into a dict from DB for quick lookup
        try:
            ensure_sqlite_db()
            conn = sqlite3.connect(SQLITE_DB_PATH)
            c = conn.cursor()
            c.execute("SELECT customer_name, mobile, village, aadhar FROM customers")
            for name, mobile, village, aadhar in c.fetchall():
                key = self._normalize_mobile(str(mobile or ""))
                if key:
                  self.customer_cache[key] = dict(
                    cust_name=name or "",
                    village=village or "",
                    aadhar=aadhar or ""
                )
            conn.close()
        except Exception as e:
            print(f"Failed to load customer cache: {e}")

    def fetch_customer_by_mobile(self):
        raw = self.cust_mobile.text().strip()
        mobile = self._normalize_mobile(raw)
        if not mobile:
            self.cust_name.clear(); self.cust_village.clear(); self.cust_aadhar.clear()
            self.cust_name.setFocus()
            return

        cust = self.customer_cache.get(mobile)
        if not cust:
           # Try DB on-demand
           try:
              ensure_sqlite_db()
              conn = sqlite3.connect(SQLITE_DB_PATH)
              c = conn.cursor()
              c.execute("SELECT customer_name, village, aadhar FROM customers WHERE mobile = ?", (mobile,))
              row = c.fetchone()
              conn.close()
              if row:
                 cust = {"cust_name": row[0] or "", "village": row[1] or "", "aadhar": row[2] or ""}
                 self.customer_cache[mobile] = cust  # cache it
           except Exception as e:
             print(f"Lookup error: {e}")

        if cust:
           self.cust_name.setText(cust['cust_name'])
           self.cust_village.setText(cust['village'])
           self.cust_aadhar.setText(cust['aadhar'])
        else:
            # Optional Excel fallback if you still keep Excel as a source
            # from utils import CUSTOMER_DATA_FILE
            try:
                if os.path.exists(CUSTOMER_DATA_FILE):
                   wb = load_workbook(CUSTOMER_DATA_FILE, read_only=True, data_only=True)
                   if "Customers" in wb.sheetnames:
                      ws = wb["Customers"]
                      for row in ws.iter_rows(min_row=2, values_only=True):
                          name, mob, village, aadhar, *_ = row
                          if self._normalize_mobile(str(mob or "")) == mobile:
                              self.cust_name.setText(str(name or ""))
                              self.cust_village.setText(str(village or ""))
                              self.cust_aadhar.setText(str(aadhar or ""))
                              break
                   wb.close()
            except Exception as e:
              print(f"Excel fallback lookup error: {e}")

        self.cust_name.setFocus()

    def add_product_to_list(self):
        pname = self.product_name_input.text().strip()
        try:
            qty = float(self.product_qty_input.text().strip())
            price = float(self.product_price_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Quantity and Price must be valid numbers.")
            return

        if not pname:
            QMessageBox.warning(self, "Input Error", "Product name cannot be empty.")
            return
        if qty <= 0 or price <= 0:
            QMessageBox.warning(self, "Input Error", "Quantity and Price must be positive.")
            return

        amount = qty * price
        self.current_products.append({
            "Product Name": pname,
            "Quantity": qty,
            "Sale Price": price,
        })

        row = self.products_table.rowCount()
        self.products_table.insertRow(row)
        self.products_table.setItem(row, 0, QTableWidgetItem(pname))
        self.products_table.setItem(row, 1, QTableWidgetItem(str(qty)))
        self.products_table.setItem(row, 2, QTableWidgetItem(f"{price:.2f}"))
        self.products_table.setItem(row, 3, QTableWidgetItem(f"{amount:.2f}"))

        self.update_total_label()

        # Clear product inputs and set focus back to product name
        self.product_name_input.clear()
        self.product_qty_input.clear()
        self.product_price_input.clear()
        self.product_name_input.setFocus()

    def update_total_label(self):
        total = sum(p["Quantity"] * p["Sale Price"] for p in self.current_products)
        discount_text = self.discount_input.text().strip()
        try:
            discount = float(discount_text) if discount_text else 0.0
        except:
            discount = 0.0
        total_after_discount = max(0.0, total - discount)
        self.total_label.setText(f"Total: ₹{total_after_discount:.2f}")

    def autofill_payment_amounts(self):
        payment_mode = self.payment_mode_combo.currentText()
        total_text = self.total_label.text().replace("Total: ₹", "")
        try:
            total = float(total_text)
        except:
            total = 0.0
        if payment_mode == "Cash":
            self.cash_amount_input.setText(f"{total:.2f}")
            self.upi_amount_input.setText("0")
        elif payment_mode == "UPI":
            self.upi_amount_input.setText(f"{total:.2f}")
            self.cash_amount_input.setText("0")
        else:  # Both
            self.cash_amount_input.setText("0")
            self.upi_amount_input.setText("0")

    def save_and_print_bill(self):
        cust_name = self.cust_name.text().strip()
        mobile = self.cust_mobile.text().strip()
        village = self.cust_village.text().strip()
        aadhar = self.cust_aadhar.text().strip()
        discount_text = self.discount_input.text().strip()
        payment_mode = self.payment_mode_combo.currentText()
        cash_text = self.cash_amount_input.text().strip()
        upi_text = self.upi_amount_input.text().strip()

        if not cust_name or not mobile:
            QMessageBox.warning(self, "Input Error", "Customer Name and Mobile number are required.")
            return
        if not self.current_products:
            QMessageBox.warning(self, "Input Error", "Add at least one product to sale.")
            return
        try:
            discount = float(discount_text)
            if discount < 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Discount must be zero or positive number.")
            return
        try:
            cash_amt = float(cash_text)
            upi_amt = float(upi_text)
            if cash_amt < 0 or upi_amt < 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Payment amounts must be zero or positive numbers.")
            return

        total_products_value = sum(p["Quantity"] * p["Sale Price"] for p in self.current_products)
        total_payable = max(0.0, total_products_value - discount)

        if abs((cash_amt + upi_amt) - total_payable) > 0.01:
            QMessageBox.warning(self, "Payment Error", "Sum of payment amounts does not match total payable.")
            return

        # Prepare data for saving
        self.last_bill_no += 1
        bill_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        products_str = "; ".join(
            f"{p['Product Name']} x{p['Quantity']} @₹{p['Sale Price']:.2f}"
            for p in self.current_products
        )

        entry_by = self.auth_manager.get_logged_in_user() if self.auth_manager else "Unknown"

        # Save to DB
        bill_data = (
            self.last_bill_no, bill_date, cust_name, mobile, village, aadhar,
            products_str, total_products_value, discount,
            total_products_value * 0.18,  # Example GST 18%, adjust if needed
            total_payable, payment_mode,
            cash_amt, upi_amt, entry_by
        )
        insert_bill_into_db(bill_data)

        # Save/update customer info in DB
        cust_info = {
            "cust_name": cust_name,
            "mobile": mobile,
            "village": village,
            "aadhar": aadhar,
            "entry_by": entry_by,
            "created_at": bill_date,
        }
        insert_or_update_customer_in_db(cust_info)

        # Reduce stock quantities from purchase stock DB
        reduce_stock_in_db(self.current_products)

        QMessageBox.information(self, "Success", f"Bill #{self.last_bill_no} saved successfully!")

        # Reset UI for next bill
        self.reset_all_fields()
        mobile = self._normalize_mobile(self.cust_mobile.text().strip())
        # use this normalized mobile for DB insert/update and validation

    def reset_all_fields(self):
        self.cust_name.clear()
        self.cust_mobile.clear()
        self.cust_village.clear()
        self.cust_aadhar.clear()
        self.discount_input.setText("0")
        self.payment_mode_combo.setCurrentIndex(0)
        self.cash_amount_input.setText("0")
        self.upi_amount_input.setText("0")
        self.current_products.clear()
        self.products_table.setRowCount(0)
        self.update_total_label()
        self.cust_mobile.setFocus()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # You can pass your purchase_excel_path_func from purchases.py here
    widget = SalesWidget(purchase_excel_path_func=purchase_excel_path)
    widget.setWindowTitle("Sales Billing System")
    widget.resize(900, 600)
    widget.show()
    sys.exit(app.exec_())
