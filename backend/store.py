import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return secrets.token_hex(12)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def check_password(password, salt, hashed):
    return hmac.compare_digest(password_hash(password, salt), hashed)


class Store:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "chanzhi.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE, name TEXT, role TEXT,
                    salt TEXT, hash TEXT, school_code TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY, kind TEXT, owner TEXT, data TEXT, created TEXT, updated TEXT);
                CREATE INDEX IF NOT EXISTS entity_kind ON entities(kind, owner);
                CREATE TABLE IF NOT EXISTS job_versions (
                    job_id TEXT, version INTEGER, data TEXT, created TEXT,
                    PRIMARY KEY(job_id, version));
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, actor TEXT, action TEXT, target TEXT, created TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, ident, kind=None):
        with self.connect() as db:
            row = db.execute("SELECT * FROM entities WHERE id=?", (ident,)).fetchone()
        if row is None or kind and row["kind"] != kind:
            return None
        return {**dict(row), "data": json.loads(row["data"])}

    def list(self, kind, owner=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM entities WHERE kind=?" + (" AND owner=?" if owner else "") + " ORDER BY created DESC", (kind, owner) if owner else (kind,)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def save(self, kind, owner, data, ident=None):
        ident = ident or uid()
        stamp = now()
        with self.connect() as db:
            db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated", (ident, kind, owner, encode(data), stamp, stamp))
        return ident

    def audit(self, actor, action, target):
        with self.connect() as db:
            db.execute("INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)", (actor, action, target, now()))
