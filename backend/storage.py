import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional


class BreakValidationError(Exception):
    """Raised when a break configuration fails validation."""


class BreakNotFoundError(Exception):
    """Raised when attempting to access a non-existent break."""


class BreakStore:
    """SQLite-backed persistence for break schedules."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS break_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    break_id INTEGER,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    change_type TEXT NOT NULL,
                    changed_by TEXT DEFAULT '',
                    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (break_id) REFERENCES breaks(id) ON DELETE CASCADE
                );
                """
            )

    def seed_from_json(self, json_path: str, changed_by: str = "seed") -> None:
        """Populate the database from an existing JSON file if no active entries exist."""
        if not os.path.exists(json_path):
            return

        with self._lock, self._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM breaks WHERE is_deleted = 0"
            ).fetchone()[0]
            if count > 0:
                return

            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            raw_breaks = payload.get("breaks", [])
            for item in raw_breaks:
                start = item.get("start")
                end = item.get("end")
                description = item.get("description", item.get("name", ""))
                break_id = item.get("id")
                if start is None or end is None:
                    continue
                inserted_id = self._insert_break(
                    conn,
                    start_time=start,
                    end_time=end,
                    description=description,
                    break_id=break_id,
                )
                self._insert_revision(
                    conn,
                    break_id=inserted_id,
                    start_time=start,
                    end_time=end,
                    description=description,
                    change_type="seed",
                    changed_by=changed_by,
                )

    def list_breaks(self, include_deleted: bool = False) -> List[Dict]:
        """Return breaks ordered by start time."""
        query = """
            SELECT id, start_time AS start, end_time AS end, description, is_deleted
            FROM breaks
            {where_clause}
            ORDER BY start_time ASC, id ASC
        """.format(
            where_clause="" if include_deleted else "WHERE is_deleted = 0"
        )

        with self._lock, self._get_conn() as conn:
            rows = conn.execute(query).fetchall()

        return [
            {
                "id": row["id"],
                "start": row["start"],
                "end": row["end"],
                "description": row["description"],
                "is_deleted": bool(row["is_deleted"]),
            }
            for row in rows
        ]

    def create_break(
        self, start: str, end: str, description: str, changed_by: str
    ) -> Dict:
        with self._lock, self._get_conn() as conn:
            self._validate_time_range(conn, start, end)
            break_id = self._insert_break(
                conn, start_time=start, end_time=end, description=description
            )
            self._insert_revision(
                conn,
                break_id=break_id,
                start_time=start,
                end_time=end,
                description=description,
                change_type="create",
                changed_by=changed_by,
            )
            row = conn.execute(
                "SELECT id, start_time AS start, end_time AS end, description "
                "FROM breaks WHERE id = ?",
                (break_id,),
            ).fetchone()

        return dict(row)

    def update_break(
        self, break_id: int, start: str, end: str, description: str, changed_by: str
    ) -> Dict:
        with self._lock, self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id, start_time, end_time, description, is_deleted "
                "FROM breaks WHERE id = ?",
                (break_id,),
            ).fetchone()
            if existing is None or existing["is_deleted"]:
                raise BreakNotFoundError(f"Break {break_id} not found")

            self._validate_time_range(conn, start, end, exclude_id=break_id)

            conn.execute(
                """
                UPDATE breaks
                SET start_time = ?, end_time = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (start, end, description, break_id),
            )
            self._insert_revision(
                conn,
                break_id=break_id,
                start_time=start,
                end_time=end,
                description=description,
                change_type="update",
                changed_by=changed_by,
            )
            row = conn.execute(
                "SELECT id, start_time AS start, end_time AS end, description "
                "FROM breaks WHERE id = ?",
                (break_id,),
            ).fetchone()

        return dict(row)

    def delete_break(self, break_id: int, changed_by: str) -> None:
        with self._lock, self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id, start_time, end_time, description, is_deleted "
                "FROM breaks WHERE id = ?",
                (break_id,),
            ).fetchone()
            if existing is None or existing["is_deleted"]:
                raise BreakNotFoundError(f"Break {break_id} not found")

            conn.execute(
                """
                UPDATE breaks
                SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (break_id,),
            )
            self._insert_revision(
                conn,
                break_id=break_id,
                start_time=existing["start_time"],
                end_time=existing["end_time"],
                description=existing["description"],
                change_type="delete",
                changed_by=changed_by,
            )

    def list_revisions(self, break_id: Optional[int] = None) -> List[Dict]:
        query = """
            SELECT id, break_id, start_time AS start, end_time AS end,
                   description, change_type, changed_by, changed_at
            FROM break_revisions
            {where_clause}
            ORDER BY changed_at DESC, id DESC
        """.format(
            where_clause="WHERE break_id = ?" if break_id else ""
        )

        params: Iterable = (break_id,) if break_id else ()
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def restore_revision(self, revision_id: int, changed_by: str) -> Dict:
        with self._lock, self._get_conn() as conn:
            revision = conn.execute(
                """
                SELECT break_id, start_time, end_time, description
                FROM break_revisions
                WHERE id = ?
                """,
                (revision_id,),
            ).fetchone()
            if revision is None:
                raise BreakNotFoundError(f"Revision {revision_id} not found")

            break_id = revision["break_id"]
            if break_id is None:
                raise BreakNotFoundError("Revision missing break reference")

            self._validate_time_range(
                conn,
                revision["start_time"],
                revision["end_time"],
                exclude_id=break_id,
            )

            conn.execute(
                """
                UPDATE breaks
                SET start_time = ?, end_time = ?, description = ?, is_deleted = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    revision["start_time"],
                    revision["end_time"],
                    revision["description"],
                    break_id,
                ),
            )
            self._insert_revision(
                conn,
                break_id=break_id,
                start_time=revision["start_time"],
                end_time=revision["end_time"],
                description=revision["description"],
                change_type="restore",
                changed_by=changed_by,
            )
            row = conn.execute(
                "SELECT id, start_time AS start, end_time AS end, description "
                "FROM breaks WHERE id = ?",
                (break_id,),
            ).fetchone()

        return dict(row)

    def _insert_break(
        self,
        conn: sqlite3.Connection,
        *,
        start_time: str,
        end_time: str,
        description: str,
        break_id: Optional[int] = None,
    ) -> int:
        if break_id is None:
            cursor = conn.execute(
                """
                INSERT INTO breaks (start_time, end_time, description)
                VALUES (?, ?, ?)
                """,
                (start_time, end_time, description),
            )
            return cursor.lastrowid

        conn.execute(
            """
            INSERT INTO breaks (id, start_time, end_time, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                description = excluded.description,
                is_deleted = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (break_id, start_time, end_time, description),
        )
        return break_id

    def _insert_revision(
        self,
        conn: sqlite3.Connection,
        *,
        break_id: int,
        start_time: str,
        end_time: str,
        description: str,
        change_type: str,
        changed_by: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO break_revisions (
                break_id, start_time, end_time, description, change_type, changed_by
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (break_id, start_time, end_time, description, change_type, changed_by),
        )

    def _validate_time_range(
        self,
        conn: sqlite3.Connection,
        start: str,
        end: str,
        *,
        exclude_id: Optional[int] = None,
    ) -> None:
        start_minutes = _time_to_minutes(start)
        end_minutes = _time_to_minutes(end)
        if start_minutes >= end_minutes:
            raise BreakValidationError("Start time must be earlier than end time")

        query = """
            SELECT id, start_time, end_time
            FROM breaks
            WHERE is_deleted = 0
        """
        params: List = []
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        rows = conn.execute(query, params).fetchall()
        for row in rows:
            existing_start = _time_to_minutes(row["start_time"])
            existing_end = _time_to_minutes(row["end_time"])
            if _ranges_overlap(start_minutes, end_minutes, existing_start, existing_end):
                raise BreakValidationError(
                    f"Break overlaps with existing break {row['id']} "
                    f"({row['start_time']} - {row['end_time']})"
                )


def _time_to_minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":")
        h = int(hours)
        m = int(minutes)
    except (ValueError, AttributeError) as exc:
        raise BreakValidationError("Time must be in HH:MM format") from exc

    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise BreakValidationError("Time values must be within 00:00-23:59")

    return h * 60 + m


def _ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)
