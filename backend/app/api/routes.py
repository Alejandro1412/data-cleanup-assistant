from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.api.schemas import (
    BulkReviewRequest,
    DatasetDetail,
    DatasetSummary,
    HealthOut,
    ReviewRequest,
    RowsPage,
    SuggestionOut,
)
from app.dependencies import get_service
from app.domain.models import Status
from app.services import DatasetNotReady, DatasetService, Export, UploadRejected
from app.storage.repository import NotFoundError

router = APIRouter(prefix="/api")
Service = Annotated[DatasetService, Depends(get_service)]


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found.")


def _csv_download(export: Export) -> Response:
    return Response(
        content=export.content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@router.get("/health")
def health(service: Service) -> HealthOut:
    return HealthOut(status="ok", ai_enabled=service.ai_enabled)


@router.post("/datasets", status_code=status.HTTP_202_ACCEPTED)
async def upload_dataset(
    file: UploadFile, background: BackgroundTasks, service: Service
) -> DatasetSummary:
    content = await file.read()
    try:
        record = service.upload(file.filename or "upload.csv", content)
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    background.add_task(service.analyze, record.id)
    return DatasetSummary.from_record(record)


@router.get("/datasets")
def list_datasets(service: Service) -> list[DatasetSummary]:
    return [DatasetSummary.from_record(r) for r in service.list_recent()]


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, service: Service) -> DatasetDetail:
    try:
        return DatasetDetail.from_record(service.get(dataset_id))
    except NotFoundError:
        raise _not_found() from None


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, service: Service) -> None:
    try:
        service.delete(dataset_id)
    except NotFoundError:
        raise _not_found() from None


@router.get("/datasets/{dataset_id}/rows")
def get_rows(
    dataset_id: str,
    service: Service,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RowsPage:
    try:
        record = service.get(dataset_id)
    except NotFoundError:
        raise _not_found() from None
    frame = service.load_frame(record)
    page = frame.iloc[offset : offset + limit]
    return RowsPage(
        columns=[str(c) for c in frame.columns],
        total=len(frame),
        offset=offset,
        rows=[
            {"index": int(i), "values": [str(x) for x in row]}
            for i, row in zip(page.index, page.itertuples(index=False), strict=True)
        ],
    )


@router.get("/datasets/{dataset_id}/suggestions")
def list_suggestions(dataset_id: str, service: Service) -> list[SuggestionOut]:
    try:
        return [SuggestionOut.from_domain(s) for s in service.suggestions(dataset_id)]
    except NotFoundError:
        raise _not_found() from None
    except DatasetNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/datasets/{dataset_id}/suggestions/{suggestion_id}")
def review_suggestion(
    dataset_id: str, suggestion_id: str, body: ReviewRequest, service: Service
) -> SuggestionOut:
    if body.final_value is not None and body.status is not Status.ACCEPTED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A custom value can only be accepted."
        )
    try:
        [updated] = service.review(dataset_id, [suggestion_id], body.status, body.final_value)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suggestion not found.") from None
    except DatasetNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SuggestionOut.from_domain(updated)


@router.post("/datasets/{dataset_id}/suggestions/bulk")
def bulk_review(dataset_id: str, body: BulkReviewRequest, service: Service) -> list[SuggestionOut]:
    try:
        updated = service.review(dataset_id, body.ids, body.status)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suggestion not found.") from None
    except DatasetNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return [SuggestionOut.from_domain(s) for s in updated]


@router.get("/datasets/{dataset_id}/export")
def export_cleaned(dataset_id: str, service: Service) -> Response:
    try:
        return _csv_download(service.export_cleaned(dataset_id))
    except NotFoundError:
        raise _not_found() from None
    except DatasetNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/datasets/{dataset_id}/audit")
def export_audit(dataset_id: str, service: Service) -> Response:
    try:
        return _csv_download(service.export_audit(dataset_id))
    except NotFoundError:
        raise _not_found() from None
    except DatasetNotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
