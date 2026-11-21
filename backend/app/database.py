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
        columns = {row[1] for row in connection.execute("PRAGMA table_info(complaints)").fetchall()}
        migrations = {
            "voice_session_id": "ALTER TABLE complaints ADD COLUMN voice_session_id TEXT",
            "confirmation_status": "ALTER TABLE complaints ADD COLUMN confirmation_status TEXT NOT NULL DEFAULT 'confirmed'",
            "proof_filename": "ALTER TABLE complaints ADD COLUMN proof_filename TEXT",
            "proof_content_type": "ALTER TABLE complaints ADD COLUMN proof_content_type TEXT",
            "proof_size": "ALTER TABLE complaints ADD COLUMN proof_size INTEGER",
        }
        for column, sql in migrations.items():
            if column not in columns:
                connection.execute(sql)

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_transcripts (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_session_id TEXT NOT NULL,
                speaker TEXT NOT NULL,
                text TEXT NOT NULL,
                is_final INTEGER NOT NULL DEFAULT 1,
                timestamp TEXT NOT NULL
            )
            """
        )


def create_complaint(payload: ComplaintCreate) -> ComplaintOut:
    now = datetime.now(timezone.utc)
    complaint_id = f"NM-{now:%y%m%d}-{uuid4().hex[:5].upper()}"
    with _connect() as connection:
        connection.execute(
            """INSERT INTO complaints
               (complaint_id, category, description, area, landmark, status, created_at,
                voice_session_id, confirmation_status)
               VALUES (?, ?, ?, ?, ?, 'RECEIVED', ?, ?, ?)""",
            (
                complaint_id,
                payload.category.value,
                payload.description,
                payload.area,
                payload.landmark,
                now.isoformat(),
                payload.voice_session_id,
                payload.confirmation_status or "confirmed",
            ),
        )
    return get_complaint(complaint_id)  # type: ignore[return-value]


def append_transcript_entry(agent_session_id: str, speaker: str, text: str, is_final: bool = True) -> dict:
    now = datetime.now(timezone.utc)
    with _connect() as connection:
        cursor = connection.execute(
            """INSERT INTO voice_transcripts
               (agent_session_id, speaker, text, is_final, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_session_id, speaker, text, int(is_final), now.isoformat()),
        )
        entry_id = cursor.lastrowid
    return {
        "entry_id": entry_id,
        "speaker": speaker,
        "text": text,
        "is_final": is_final,
        "timestamp": now,
    }


def list_transcript_entries(agent_session_id: str) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            """SELECT entry_id, speaker, text, is_final, timestamp
               FROM voice_transcripts
               WHERE agent_session_id = ?
               ORDER BY entry_id ASC""",
            (agent_session_id,),
        ).fetchall()
    return [
        {
            "entry_id": row["entry_id"],
            "speaker": row["speaker"],
            "text": row["text"],
            "is_final": bool(row["is_final"]),
            "timestamp": datetime.fromisoformat(row["timestamp"]),
        }
        for row in rows
    ]


def _complaint_from_row(row: sqlite3.Row) -> ComplaintOut:
    keys = row.keys()
    proof_filename = row["proof_filename"] if "proof_filename" in keys else None
    return ComplaintOut(
        complaint_id=row["complaint_id"],
        category=ComplaintCategory(row["category"]),
        description=row["description"],
        area=row["area"],
        landmark=row["landmark"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        voice_session_id=row["voice_session_id"] if "voice_session_id" in keys else None,
        confirmation_status=row["confirmation_status"] if "confirmation_status" in keys else "confirmed",
        proof_filename=proof_filename,
        proof_content_type=row["proof_content_type"] if "proof_content_type" in keys else None,
        proof_size=row["proof_size"] if "proof_size" in keys else None,
        proof_url=f"/api/complaints/{row['complaint_id']}/proof" if proof_filename else None,
    )


def get_complaint(complaint_id: str) -> ComplaintOut | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id.upper(),)
        ).fetchone()
    if row is None:
        return None
    return _complaint_from_row(row)


def list_complaints(limit: int = 50) -> list[ComplaintOut]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM complaints ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_complaint_from_row(row) for row in rows]


def attach_proof(complaint_id: str, filename: str, content_type: str | None, size: int) -> ComplaintOut | None:
    with _connect() as connection:
        cursor = connection.execute(
            """UPDATE complaints
               SET proof_filename = ?, proof_content_type = ?, proof_size = ?
               WHERE complaint_id = ?""",
            (filename, content_type, size, complaint_id.upper()),
        )
        if cursor.rowcount == 0:
            return None
    return get_complaint(complaint_id)


def update_complaint_status(complaint_id: str, status: str) -> ComplaintOut | None:
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE complaints SET status = ? WHERE complaint_id = ?",
            (status, complaint_id.upper()),
        )
        if cursor.rowcount == 0:
            return None
    return get_complaint(complaint_id)
