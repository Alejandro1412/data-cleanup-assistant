"""SQLite persistence.

SQLite is enough for a single-user tool and needs no setup. All SQL lives in
this module, so moving to Postgres means changing this file only.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.models import (
    Action,
    DatasetStatus,
    IssueKind,
    Source,
    Status,
    Suggestion,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id            TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    status        TEXT NOT NULL,
    progress      TEXT,
    error         TEXT,
    encoding      TEXT,
    delimiter     TEXT,
    row_count     INTEGER NOT NULL DEFAULT 0,
    columns_json  TEXT NOT NULL DEFAULT '[]',
    profile_json  TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    ai_model      TEXT,
    file_path     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id                TEXT PRIMARY KEY,
    dataset_id        TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    kind              TEXT NOT NULL,
    action            TEXT NOT NULL,
    row_index         INTEGER NOT NULL,
    column_name       TEXT,
    current_value     TEXT,
    proposed_value    TEXT,
    final_value       TEXT,
    related_row_index INTEGER,
    reason            TEXT NOT NULL,
    confidence        REAL NOT NULL,
    source            TEXT NOT NULL,
    group_key         TEXT NOT NULL,
    status            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_dataset ON suggestions(dataset_id, position);

CREATE TABLE IF NOT EXISTS llm_cache (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass
class DatasetRecord:
    id: str
    filename: str
    created_at: str
    status: DatasetStatus
    file_path: str
    progress: str | None = None
    error: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    profile: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ai_model: str | None = None


class NotFoundError(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per operation keeps this safe to call from
        # the request threads and the background analysis thread at once.
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Datasets

    def create_dataset(self, dataset_id: str, filename: str, file_path: Path) -> DatasetRecord:
        record = DatasetRecord(
            id=dataset_id,
            filename=filename,
            created_at=_now(),
            status=DatasetStatus.QUEUED,
            file_path=str(file_path),
            progress="Waiting to start",
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO datasets (id, filename, created_at, status, progress, file_path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.filename,
                    record.created_at,
                    record.status.value,
                    record.progress,
                    record.file_path,
                ),
            )
        return record

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise NotFoundError(dataset_id)
        return DatasetRecord(
            id=row["id"],
            filename=row["filename"],
            created_at=row["created_at"],
            status=DatasetStatus(row["status"]),
            file_path=row["file_path"],
            progress=row["progress"],
            error=row["error"],
            encoding=row["encoding"],
            delimiter=row["delimiter"],
            row_count=row["row_count"],
            columns=json.loads(row["columns_json"]),
            profile=json.loads(row["profile_json"]),
            warnings=json.loads(row["warnings_json"]),
            ai_model=row["ai_model"],
        )

    def list_datasets(self, limit: int = 20) -> list[DatasetRecord]:
        with self._connect() as conn:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM datasets ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            ]
        return [self.get_dataset(i) for i in ids]

    def update_progress(self, dataset_id: str, status: DatasetStatus, progress: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE datasets SET status = ?, progress = ? WHERE id = ?",
                (status.value, progress, dataset_id),
            )

    def mark_failed(self, dataset_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE datasets SET status = ?, error = ?, progress = NULL WHERE id = ?",
                (DatasetStatus.FAILED.value, error, dataset_id),
            )

    def save_analysis(
        self,
        dataset_id: str,
        *,
        encoding: str,
        delimiter: str,
        row_count: int,
        columns: list[str],
        profile: list[dict[str, Any]],
        warnings: list[str],
        ai_model: str | None,
        suggestions: list[Suggestion],
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM suggestions WHERE dataset_id = ?", (dataset_id,))
            conn.executemany(
                "INSERT INTO suggestions (id, dataset_id, position, kind, action, row_index, "
                "column_name, current_value, proposed_value, final_value, related_row_index, "
                "reason, confidence, source, group_key, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        s.id,
                        dataset_id,
                        position,
                        s.kind.value,
                        s.action.value,
                        s.row_index,
                        s.column,
                        s.current_value,
                        s.proposed_value,
                        s.final_value,
                        s.related_row_index,
                        s.reason,
                        s.confidence,
                        s.source.value,
                        s.group_key,
                        s.status.value,
                    )
                    for position, s in enumerate(suggestions)
                ],
            )
            conn.execute(
                "UPDATE datasets SET status = ?, progress = NULL, error = NULL, encoding = ?, "
                "delimiter = ?, row_count = ?, columns_json = ?, profile_json = ?, "
                "warnings_json = ?, ai_model = ? WHERE id = ?",
                (
                    DatasetStatus.READY.value,
                    encoding,
                    delimiter,
                    row_count,
                    json.dumps(columns),
                    json.dumps(profile),
                    json.dumps(warnings),
                    ai_model,
                    dataset_id,
                ),
            )

    def delete_dataset(self, dataset_id: str) -> DatasetRecord:
        record = self.get_dataset(dataset_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        return record

    # Suggestions

    def list_suggestions(self, dataset_id: str) -> list[Suggestion]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM suggestions WHERE dataset_id = ? ORDER BY position", (dataset_id,)
            ).fetchall()
        return [_to_suggestion(r) for r in rows]

    def update_suggestions(
        self,
        dataset_id: str,
        ids: list[str],
        status: Status,
        final_value: str | None = None,
        clear_final_value: bool = False,
    ) -> list[Suggestion]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        assignments = "status = ?"
        params: list[Any] = [status.value]
        if final_value is not None or clear_final_value:
            assignments += ", final_value = ?"
            params.append(final_value)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE suggestions SET {assignments} "
                f"WHERE dataset_id = ? AND id IN ({placeholders})",
                [*params, dataset_id, *ids],
            )
            if cursor.rowcount != len(set(ids)):
                raise NotFoundError("One or more suggestions do not belong to this dataset.")
            rows = conn.execute(
                f"SELECT * FROM suggestions WHERE dataset_id = ? AND id IN ({placeholders}) "
                "ORDER BY position",
                [dataset_id, *ids],
            ).fetchall()
        return [_to_suggestion(r) for r in rows]

    # LLM cache (implements app.llm.cache.CacheStore)

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value_json FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, value_json, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), _now()),
            )


def _to_suggestion(row: sqlite3.Row) -> Suggestion:
    return Suggestion(
        id=row["id"],
        kind=IssueKind(row["kind"]),
        action=Action(row["action"]),
        row_index=row["row_index"],
        column=row["column_name"],
        current_value=row["current_value"],
        proposed_value=row["proposed_value"],
        final_value=row["final_value"],
        related_row_index=row["related_row_index"],
        reason=row["reason"],
        confidence=row["confidence"],
        source=Source(row["source"]),
        group_key=row["group_key"],
        status=Status(row["status"]),
    )
