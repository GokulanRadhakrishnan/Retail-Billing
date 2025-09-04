import bcrypt
import json
import os
import time

USERS_FILE = "users.json"
SESSION_TIMEOUT_SECONDS = 15 * 60  # 15 minutes inactivity timeout

class AuthError(Exception):
    pass

class AuthManager:
    def __init__(self):
        # Load users from JSON file or create default admin user
        self.users = {}  # username: dict with password_hash & roles
        self.current_user = None
        self.current_role = None
        self.last_activity = None  # timestamp for session timeout
        
        self.load_users()

    def load_users(self):
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r") as f:
                    data = json.load(f)
                    self.users = data.get("users", {})
            except Exception as e:
                print(f"Error loading users file: {e}")
                self.users = {}
        if "admin" not in self.users:
            # Create default admin with password "admin123"
            print("Creating default admin user")
            self.add_user("admin", "admin123", roles=["admin"])
            self.save_users()

    def save_users(self):
        try:
            with open(USERS_FILE, "w") as f:
                json.dump({"users": self.users}, f, indent=4)
        except Exception as e:
            print(f"Error saving users file: {e}")

    def hash_password(self, password: str) -> bytes:
        # Generate bcrypt salt and hashed password
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    def check_password(self, password: str, hashed: bytes) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed)
        except Exception:
            return False

    def add_user(self, username: str, password: str, roles=None):
        if roles is None:
            roles = ["staff"]  # default role
        if username in self.users:
            raise AuthError(f"User '{username}' already exists.")
        pwd_hash = self.hash_password(password)
        self.users[username] = {"password_hash": pwd_hash.decode("utf-8"), "roles": roles}
        self.save_users()

    def update_password(self, username: str, new_password: str):
        if username not in self.users:
            raise AuthError(f"User '{username}' does not exist.")
        pwd_hash = self.hash_password(new_password)
        self.users[username]["password_hash"] = pwd_hash.decode("utf-8")
        self.save_users()

    def delete_user(self, username: str):
        if username not in self.users:
            raise AuthError(f"User '{username}' does not exist.")
        if username == "admin":
            raise AuthError("Cannot delete default admin user.")
        del self.users[username]
        self.save_users()

    def login(self, username: str, password: str) -> bool:
        if username not in self.users:
            return False
        stored_hash = self.users[username]["password_hash"].encode("utf-8")
        if self.check_password(password, stored_hash):
            self.current_user = username
            self.current_role = self.get_user_roles(username)
            self.last_activity = time.time()
            return True
        return False

    def logout(self):
        self.current_user = None
        self.current_role = None
        self.last_activity = None

    def is_logged_in(self) -> bool:
        return self.current_user is not None

    def get_current_user(self):
        if not self.is_logged_in():
            return None
        return self.current_user

    def get_user_roles(self, username: str):
        return self.users.get(username, {}).get("roles", [])

    def has_role(self, role: str) -> bool:
        if not self.is_logged_in():
            return False
        return role in self.current_role

    def check_session_timeout(self) -> bool:
        if not self.is_logged_in():
            return False
        if (time.time() - self.last_activity) > SESSION_TIMEOUT_SECONDS:
            self.logout()
            return True
        self.last_activity = time.time()
        return False

    # Password rule checks (can be used during registration or password changes)
    def validate_password_rules(self, password: str) -> tuple[bool, str]:
        if len(password) < 8:
            return False, "Password must be at least 8 characters long."
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter."
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter."
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit."
        if not any(c in "!@#$%^&*()-_=+[{]}\\|;:'\",<.>/?`~" for c in password):
            return False, "Password must contain at least one special character."
        return True, ""

# Example usage:
if __name__ == "__main__":
    auth = AuthManager()
    
    print("Users loaded:", list(auth.users.keys()))
    
    # Add a test user (will error if user exists)
    try:
        auth.add_user("testuser", "Testuser@123", roles=["staff"])
        print("Test user added")
    except AuthError as e:
        print(e)
    
    # Login test
    success = auth.login("testuser", "Testuser@123")
    print("Login successful:", success)
    print("Current user:", auth.get_current_user())
    print("Has admin role:", auth.has_role("admin"))

    # Logout test
    auth.logout()
    print("Logged out. Current user:", auth.get_current_user())
