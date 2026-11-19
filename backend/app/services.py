"""Application use cases. The HTTP layer calls these and nothing else."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.config import Settings
from app.domain.models import DatasetStatus, Status, Suggestion
from app.llm.reviewer import AIReviewer
from app.pipeline.analyzer import Analyzer
from app.pipeline.apply import (
    AuditEntry,
    apply_suggestions,
    audit_to_csv_bytes,
    to_csv_bytes,
)
from app.pipeline.ingest import IngestError, load_csv
from app.storage.repository import DatasetRecord, Repository

logger = logging.getLogger(__name__)


class UploadRejected(ValueError):
    pass


class DatasetNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class Export:
    filename: str
    content: bytes


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "dataset"


class DatasetService:
    def __init__(
        self, settings: Settings, repository: Repository, reviewer: AIReviewer | None
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._reviewer = reviewer
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ai_enabled(self) -> bool:
        return self._reviewer is not None

    def upload(self, filename: str, content: bytes) -> DatasetRecord:
        if not filename.lower().endswith((".csv", ".tsv", ".txt")):
            raise UploadRejected("Only .csv, .tsv and .txt files are supported.")
        max_bytes = self._settings.max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise UploadRejected(f"The file is larger than {self._settings.max_upload_mb} MB.")
        try:
            # Parse now so a broken file is rejected in the upload response
            # instead of failing later in the background.
            load_csv(content, self._settings.max_rows)
        except IngestError as exc:
            raise UploadRejected(str(exc)) from exc

        dataset_id = uuid.uuid4().hex
        path = self._settings.uploads_dir / f"{dataset_id}.csv"
        path.write_bytes(content)
        return self._repo.create_dataset(dataset_id, Path(filename).name, path)

    def analyze(self, dataset_id: str) -> None:
        """Runs in a background thread; every failure ends up on the dataset record."""

        def progress(message: str) -> None:
            self._repo.update_progress(dataset_id, DatasetStatus.ANALYZING, message)

        try:
            progress("Reading file")
            record = self._repo.get_dataset(dataset_id)
            loaded = load_csv(Path(record.file_path).read_bytes(), self._settings.max_rows)
            result = Analyzer(self._settings, self._reviewer).run(loaded.frame, progress)
            self._repo.save_analysis(
                dataset_id,
                encoding=loaded.encoding,
                delimiter=loaded.delimiter,
                row_count=len(loaded.frame),
                columns=[str(c) for c in loaded.frame.columns],
                profile=[p.to_dict() for p in result.profiles.values()],
                warnings=result.warnings,
                ai_model=self._reviewer.model if self._reviewer else None,
                suggestions=result.suggestions,
            )
        except Exception as exc:
            logger.exception("Analysis failed for dataset %s", dataset_id)
            self._repo.mark_failed(dataset_id, f"Analysis failed: {exc}")

    def get(self, dataset_id: str) -> DatasetRecord:
        return self._repo.get_dataset(dataset_id)

    def list_recent(self) -> list[DatasetRecord]:
        return self._repo.list_datasets()

    def delete(self, dataset_id: str) -> None:
        record = self._repo.delete_dataset(dataset_id)
        Path(record.file_path).unlink(missing_ok=True)

    def load_frame(self, record: DatasetRecord) -> pd.DataFrame:
        return load_csv(
            Path(record.file_path).read_bytes(),
            self._settings.max_rows,
            encoding=record.encoding,
            delimiter=record.delimiter,
        ).frame

    def suggestions(self, dataset_id: str) -> list[Suggestion]:
        self._require_ready(dataset_id)
        return self._repo.list_suggestions(dataset_id)

    def review(
        self,
        dataset_id: str,
        ids: list[str],
        status: Status,
        final_value: str | None = None,
    ) -> list[Suggestion]:
        self._require_ready(dataset_id)
        # Going back to pending also discards a value the reviewer typed.
        return self._repo.update_suggestions(
            dataset_id,
            ids,
            status,
            final_value=final_value,
            clear_final_value=status is Status.PENDING,
        )

    def export_cleaned(self, dataset_id: str) -> Export:
        record, cleaned, _ = self._apply(dataset_id)
        return Export(f"{_safe_stem(record.filename)}_cleaned.csv", to_csv_bytes(cleaned))

    def export_audit(self, dataset_id: str) -> Export:
        record, _, audit = self._apply(dataset_id)
        return Export(f"{_safe_stem(record.filename)}_changes.csv", audit_to_csv_bytes(audit))

    def _apply(self, dataset_id: str) -> tuple[DatasetRecord, pd.DataFrame, list[AuditEntry]]:
        record = self._require_ready(dataset_id)
        frame = self.load_frame(record)
        cleaned, audit = apply_suggestions(frame, self._repo.list_suggestions(dataset_id))
        return record, cleaned, audit

    def _require_ready(self, dataset_id: str) -> DatasetRecord:
        record = self._repo.get_dataset(dataset_id)
        if record.status is not DatasetStatus.READY:
            raise DatasetNotReady(f"Dataset is {record.status.value}.")
        return record
