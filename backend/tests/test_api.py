from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.helpers import FakeProvider

ClientFactory = Callable[[FakeProvider | None], TestClient]

CSV = (
    "id,name,email,country,amount\n"
    "1,Ana Ruiz,ana@x.com,USA,100\n"
    "2,Luis Gil,LUIS@x.com,usa,105\n"
    "3,Eva Diaz,eva@x.com,USA,N/A\n"
    "4,Ana Ruiz,ana@x.com,USA,100\n"
)


def _upload(client: TestClient, content: str = CSV, name: str = "people.csv") -> str:
    response = client.post("/api/datasets", files={"file": (name, content, "text/csv")})
    assert response.status_code == 202, response.text
    dataset_id: str = response.json()["id"]
    return dataset_id


def test_full_review_flow(make_client: ClientFactory) -> None:
    client = make_client(None)
    dataset_id = _upload(client)

    # TestClient runs background tasks before returning, so analysis is done.
    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["status"] == "ready"
    assert detail["row_count"] == 4
    assert [c["name"] for c in detail["profile"]] == ["id", "name", "email", "country", "amount"]

    suggestions = client.get(f"/api/datasets/{dataset_id}/suggestions").json()
    kinds = {s["kind"] for s in suggestions}
    assert {"exact_duplicate", "inconsistent_category", "missing_value"} <= kinds

    ids = [s["id"] for s in suggestions if s["action"] != "flag"]
    response = client.post(
        f"/api/datasets/{dataset_id}/suggestions/bulk", json={"ids": ids, "status": "accepted"}
    )
    assert response.status_code == 200

    export = client.get(f"/api/datasets/{dataset_id}/export")
    assert export.headers["content-disposition"] == 'attachment; filename="people_cleaned.csv"'
    assert export.text.splitlines() == [
        "id,name,email,country,amount",
        "1,Ana Ruiz,ana@x.com,USA,100",
        "2,Luis Gil,luis@x.com,USA,105",
        "3,Eva Diaz,eva@x.com,USA,",
    ]

    audit = client.get(f"/api/datasets/{dataset_id}/audit").text.splitlines()
    assert audit[0] == "suggestion_id,row,column,action,before,after,issue,source,reason"
    assert len(audit) == 1 + len(ids)


def test_custom_value_is_used_on_export(make_client: ClientFactory) -> None:
    client = make_client(None)
    dataset_id = _upload(client)
    suggestions = client.get(f"/api/datasets/{dataset_id}/suggestions").json()
    [placeholder] = [s for s in suggestions if s["current_value"] == "N/A"]

    response = client.patch(
        f"/api/datasets/{dataset_id}/suggestions/{placeholder['id']}",
        json={"status": "accepted", "final_value": "102"},
    )

    assert response.json()["final_value"] == "102"
    assert "3,Eva Diaz,eva@x.com,USA,102" in client.get(f"/api/datasets/{dataset_id}/export").text


def test_custom_value_requires_accepting(make_client: ClientFactory) -> None:
    client = make_client(None)
    dataset_id = _upload(client)
    first = client.get(f"/api/datasets/{dataset_id}/suggestions").json()[0]

    response = client.patch(
        f"/api/datasets/{dataset_id}/suggestions/{first['id']}",
        json={"status": "rejected", "final_value": "x"},
    )

    assert response.status_code == 422


def test_rejects_files_that_are_not_csv(make_client: ClientFactory) -> None:
    client = make_client(None)

    wrong_type = client.post("/api/datasets", files={"file": ("a.xlsx", b"x", "text/plain")})
    empty = client.post("/api/datasets", files={"file": ("a.csv", b"", "text/csv")})

    assert wrong_type.status_code == 422
    assert empty.status_code == 422
    assert "empty" in empty.json()["detail"]


def test_unknown_ids_return_404(make_client: ClientFactory) -> None:
    client = make_client(None)
    dataset_id = _upload(client)

    assert client.get("/api/datasets/missing").status_code == 404
    response = client.post(
        f"/api/datasets/{dataset_id}/suggestions/bulk",
        json={"ids": ["not-a-real-id"], "status": "accepted"},
    )
    assert response.status_code == 404


def test_health_reports_ai_status(make_client: ClientFactory) -> None:
    assert make_client(None).get("/api/health").json() == {"status": "ok", "ai_enabled": False}
    assert make_client(FakeProvider({})).get("/api/health").json()["ai_enabled"] is True


def test_delete_removes_dataset(make_client: ClientFactory) -> None:
    client = make_client(None)
    dataset_id = _upload(client)

    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 204
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 404
