"""Password hashing utilities using bcrypt."""
import bcrypt


def hash_password(password: str) -> str:
    """Hash a password with bcrypt and return the hash as a string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())
