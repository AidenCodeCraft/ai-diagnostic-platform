"""Seed default users if they don't exist (development only)."""

from app.database import session
from app.models.user import User


DEFAULT_USERS = [
    {
        "username": "admin",
        "password_hash": "ca1422576d89e96e6c51de81f91f72c1:7880b60bed6601309f830b7c62bf335153aec1da68ef7ae28da2da49512c9bc3",
        "role": "admin",
        "is_active": True,
    },
    {
        "username": "engineer",
        "password_hash": "854c5fc5a8f70fdc51b21e16bb490fdb:31caca4dd96263b6ec3fdd489e68665ddeaa8f19b74dbcbf76f95603b1745c50",
        "role": "engineer",
        "is_active": True,
    },
]


def seed_users():
    """Create default users if they don't exist."""
    db = session.create_session()
    try:
        for u in DEFAULT_USERS:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if not existing:
                db.add(User(**u))
                print(f"[seed] Created user: {u['username']} (role={u['role']})")
        db.commit()
    finally:
        db.close()
