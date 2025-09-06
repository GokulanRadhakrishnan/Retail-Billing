import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMessageBox, QInputDialog, QAction, QLineEdit
)
from PyQt5.QtCore import QTimer

# Import your actual implemented modules here
from auth import AuthManager
from purchases import PurchaseWidget
from sales import SalesWidget
from customers import CustomerWidget
from admin import AdminWidget
from reports import ReportsWidget

# Import any utility functions needed (adjust import paths as per your project)
from utils import get_financial_year  # Or your exact function for financial year calculation

# Helper function to get dynamically the purchase Excel path for Sales widget
def purchase_excel_path(qdate) -> str:
    """Return purchase Excel path for given QDate."""
    # qdate is QDate instance, convert to Python datetime.date
    pydate = qdate.toPyDate()
    fy = get_financial_year(pydate)
    # Adjust if you have function or variable storing data folder and filename template
    return f"data/Purchase_{fy}.xlsx"  # Adapt path according to your project structure


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sri Krishna Agro Centre - Retail Billing Software")
        self.setGeometry(100, 100, 1200, 800)

        # Instantiate authentication manager
        self.auth_manager = AuthManager()

        # Create menu bar and tabs
        self._create_menu()
        self._create_tabs()

        # Update the UI tabs access permissions
        self._update_ui_access()

        # Prompt login on start
        self._show_login_dialog()

        # Session timeout timer (checks every 60 seconds)
        self.session_timer = QTimer(self)
        self.session_timer.setInterval(60_000)
        self.session_timer.timeout.connect(self._on_session_timer)
        self.session_timer.start()

    def _create_menu(self) -> None:
        """Create menu bar and actions."""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")
        login_action = QAction("Login", self)
        login_action.triggered.connect(self._show_login_dialog)
        logout_action = QAction("Logout", self)
        logout_action.triggered.connect(self._logout)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(login_action)
        file_menu.addAction(logout_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _create_tabs(self) -> None:
        """Create tab widgets for main sections."""
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create instances of your actual widget modules,
        # pass auth_manager or functions as needed for permissions and dependencies.

        self.purchase_tab = PurchaseWidget(auth_manager=self.auth_manager)
        self.sales_tab = SalesWidget(
            auth_manager=self.auth_manager,
            purchase_excel_path_func=purchase_excel_path  # Function to supply purchase Excel path
        )
        self.admin_tab = AdminWidget(self.auth_manager)
        self.customer_tab = CustomerWidget(auth_manager=self.auth_manager)
        self.reports_tab = ReportsWidget()

        # Add tabs with proper titles:
        self.tabs.addTab(self.purchase_tab, "Purchase Section")
        self.tabs.addTab(self.sales_tab, "Sales Section")
        self.tabs.addTab(self.admin_tab, "Admin Menu")
        self.tabs.addTab(self.customer_tab, "Customer Menu")
        self.tabs.addTab(self.reports_tab, "Reports")

    def _show_login_dialog(self) -> None:
        """Show login dialog for user authentication."""
        if self.auth_manager.current_user:
            QMessageBox.information(self, "Already Logged In",
                                    f"User '{self.auth_manager.current_user}' is already logged in.")
            return

        username, ok1 = QInputDialog.getText(self, "Login", "Enter username:")
        if not ok1 or not username:
            return

        password, ok2 = QInputDialog.getText(self, "Login", "Enter password:", QLineEdit.Password)
        if not ok2 or not password:
            return

        if self.auth_manager.login(username, password):
            QMessageBox.information(self, "Login Successful", f"Welcome {username}!")
            self._update_ui_access()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password.")

    def _update_ui_access(self) -> None:
        """Update tab access based on login and role."""
        logged_in = self.auth_manager.current_user is not None
        is_admin = self.auth_manager.has_role("admin")

        # Enable tabs based on login and role
        self.tabs.setTabEnabled(self.tabs.indexOf(self.purchase_tab), logged_in)
        self.tabs.setTabEnabled(self.tabs.indexOf(self.sales_tab), logged_in)
        self.tabs.setTabEnabled(self.tabs.indexOf(self.customer_tab), logged_in)
        self.tabs.setTabEnabled(self.tabs.indexOf(self.reports_tab), logged_in)

        self.tabs.setTabEnabled(self.tabs.indexOf(self.admin_tab), is_admin)

        if not logged_in:
            QMessageBox.information(self, "Login Required", "Please login to access application features.")

    def _logout(self) -> None:
        """Logout current user."""
        if not self.auth_manager.current_user:
            QMessageBox.information(self, "Logout", "No user is currently logged in.")
            return

        confirm = QMessageBox.question(self, "Logout Confirmation", "Are you sure you want to logout?",
                                       QMessageBox.Yes | QMessageBox.No)

        if confirm == QMessageBox.Yes:
            user = self.auth_manager.current_user
            self.auth_manager.logout()
            QMessageBox.information(self, "Logged Out", f"User '{user}' logged out successfully.")
            self._update_ui_access()

    def _show_about_dialog(self) -> None:
        """Show about dialog."""
        QMessageBox.information(
            self,
            "About Your company Software",
            "Retail Billing Software for Your company\n"
            "Built with PyQt5\n"
            "Version 1.0\n"
            "© 2025 Gokulan"
        )

    def _on_session_timer(self) -> None:
        """Handle session timeout."""
        # If session timed out, AuthManager.logout() is called inside check_session_timeout
        if self.auth_manager.check_session_timeout():
            QMessageBox.information(self, "Session Timeout", "You have been logged out due to inactivity.")
            self._update_ui_access()

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        reply = QMessageBox.question(
            self,
            'Exit Application',
            'Are you sure you want to exit?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()


def main() -> None:
    """Main entry point for application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
