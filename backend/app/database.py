import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.config import get_settings
from backend.app.schemas import ComplaintCreate, ComplaintOut, ComplaintCategory


def _connect() -> sqlite3.Connection:
    path: Path = get_settings().database_file
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS complaints (
                complaint_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                area TEXT NOT NULL,
                landmark TEXT,
                status TEXT NOT NULL DEFAULT 'RECEIVED',
                created_at TEXT NOT NULL
            )
            """
        )


def create_complaint(payload: ComplaintCreate) -> ComplaintOut:
    now = datetime.now(timezone.utc)
    complaint_id = f"NM-{now:%y%m%d}-{uuid4().hex[:5].upper()}"
    with _connect() as connection:
        connection.execute(
            """INSERT INTO complaints
               (complaint_id, category, description, area, landmark, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'RECEIVED', ?)""",
            (
                complaint_id,
                payload.category.value,
                payload.description,
                payload.area,
                payload.landmark,
                now.isoformat(),
            ),
        )
    return get_complaint(complaint_id)  # type: ignore[return-value]


def get_complaint(complaint_id: str) -> ComplaintOut | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id.upper(),)
        ).fetchone()
    if row is None:
        return None
    return ComplaintOut(
        complaint_id=row["complaint_id"],
        category=ComplaintCategory(row["category"]),
        description=row["description"],
        area=row["area"],
        landmark=row["landmark"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def list_complaints(limit: int = 50) -> list[ComplaintOut]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM complaints ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        ComplaintOut(
            complaint_id=row["complaint_id"],
            category=ComplaintCategory(row["category"]),
            description=row["description"],
            area=row["area"],
            landmark=row["landmark"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def update_complaint_status(complaint_id: str, status: str) -> ComplaintOut | None:
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE complaints SET status = ? WHERE complaint_id = ?",
            (status, complaint_id.upper()),
        )
        if cursor.rowcount == 0:
            return None
    return get_complaint(complaint_id)
