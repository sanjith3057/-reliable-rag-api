from tests.conftest import PASSWORD_DOC, SAMPLE_DOCS, assert_error, upload


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["documents"] == 0
    assert body["llm"]["provider"] == "fake"


def test_ui_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_ingest_then_ask_end_to_end(client, llm):
    ingested = upload(client)
    assert ingested.status_code == 201
    assert ingested.json()["status"] == "created"
    assert ingested.json()["chunks"] >= 1

    response = client.post("/ask", json={"question": "How often must passwords be rotated?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answerable"] is True
    assert body["abstain_reason"] is None
    assert "180 days" in body["answer"] or "14 characters" in body["answer"]
    source = body["sources"][0]
    assert source["doc_name"] == "security.txt"
    assert source["page"] is None
    assert source["excerpt"] and source["excerpt"] in PASSWORD_DOC.decode().replace("\n\n", " ") + " … "
    assert 0 < source["score"] <= 1
    assert len(llm.calls) == 1


def test_excerpt_is_shorter_than_the_chunk(client):
    upload(client)
    body = client.post("/ask", json={"question": "How often must passwords be rotated?"}).json()
    assert len(body["sources"][0]["excerpt"]) < len(PASSWORD_DOC)


def test_pdf_source_reports_its_page(client):
    pdf = (SAMPLE_DOCS / "expense_policy.pdf").read_bytes()
    ingested = upload(client, "expense_policy.pdf", pdf).json()
    assert ingested["pages"] == 2

    body = client.post("/ask", json={"question": "Within how many days must expense claims be submitted?"}).json()
    assert body["answerable"] is True
    assert body["sources"][0]["doc_name"] == "expense_policy.pdf"
    assert body["sources"][0]["page"] == 2


def test_documents_list_delete_and_reset(client):
    doc_id = upload(client).json()["doc_id"]
    upload(client, "other.md", b"# Notes\n\nThe cafeteria opens at 08:00.")

    documents = client.get("/documents").json()["documents"]
    assert {doc["doc_name"] for doc in documents} == {"security.txt", "other.md"}
    assert all(doc["chunks"] >= 1 and doc["ingested_at"] for doc in documents)

    deleted = client.delete(f"/documents/{doc_id}")
    assert deleted.status_code == 200 and deleted.json()["chunks_removed"] >= 1
    assert [doc["doc_name"] for doc in client.get("/documents").json()["documents"]] == ["other.md"]
    assert_error(client.delete(f"/documents/{doc_id}"), 404, "DOCUMENT_NOT_FOUND")

    assert client.post("/reset").json()["status"] == "reset"
    assert client.get("/documents").json()["documents"] == []


def test_ingest_samples(client):
    ingested = client.post("/ingest/samples").json()
    assert len(ingested) == 8
    assert client.get("/health").json()["documents"] == 8


def test_request_id_is_echoed(client):
    response = client.get("/health", headers={"x-request-id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"
