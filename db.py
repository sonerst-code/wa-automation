"""
Basit depolama katmanı: üretimde (Render) DATABASE_URL tanımlıysa PostgreSQL kullanılır,
yerel geliştirme/testte DATABASE_URL yoksa aynı dizindeki data.db adlı SQLite dosyası
kullanılır. Böylece ek bir sunucu kurmadan yerel test edilebilir, Render'a deploy
edilince gerçek kalıcı bir veritabanına otomatik geçer.
"""

import os
import json

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3

    SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")


def get_connection():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _q(query: str) -> str:
    """SQLite'ta yazdığımız '?' placeholder'larını Postgres modunda '%s'e çevirir."""
    return query.replace("?", "%s") if USE_POSTGRES else query


def init_db() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    phone TEXT PRIMARY KEY,
                    step TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone TEXT NOT NULL,
                    name TEXT,
                    time_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    phone TEXT PRIMARY KEY,
                    step TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    name TEXT,
                    time_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        conn.commit()
    finally:
        conn.close()


def get_state(phone: str) -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(_q("SELECT step, data FROM conversations WHERE phone = ?"), (phone,))
        row = cur.fetchone()
        if row is None:
            return {"step": "NEW", "data": {}}
        step, data_json = row
        return {"step": step, "data": json.loads(data_json) if data_json else {}}
    finally:
        conn.close()


def save_state(phone: str, step: str, data: dict) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        data_json = json.dumps(data)
        if USE_POSTGRES:
            cur.execute(
                _q(
                    "INSERT INTO conversations (phone, step, data) VALUES (?, ?, ?) "
                    "ON CONFLICT (phone) DO UPDATE SET step = EXCLUDED.step, data = EXCLUDED.data"
                ),
                (phone, step, data_json),
            )
        else:
            cur.execute(
                _q("INSERT OR REPLACE INTO conversations (phone, step, data) VALUES (?, ?, ?)"),
                (phone, step, data_json),
            )
        conn.commit()
    finally:
        conn.close()


def reset_state(phone: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(_q("DELETE FROM conversations WHERE phone = ?"), (phone,))
        conn.commit()
    finally:
        conn.close()


def save_appointment(phone: str, name: str, time_text: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("INSERT INTO appointments (phone, name, time_text) VALUES (?, ?, ?)"),
            (phone, name, time_text),
        )
        conn.commit()
    finally:
        conn.close()


def list_appointments(limit: int = 50) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("SELECT phone, name, time_text, created_at FROM appointments ORDER BY id DESC LIMIT ?"),
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {"phone": r[0], "name": r[1], "time_text": r[2], "created_at": str(r[3])}
            for r in rows
        ]
    finally:
        conn.close()
