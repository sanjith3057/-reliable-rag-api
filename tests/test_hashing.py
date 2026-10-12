from app.ingestion.hashing import doc_id_for
from tests.conftest import PASSWORD_DOC, make_service


def test_same_content_gives_same_id():
    assert doc_id_for(b"hello") == doc_id_for(b"hello")
    assert doc_id_for(b"hello") != doc_id_for(b"hello!")
    assert len(doc_id_for(b"hello")) == 16


def test_ingesting_the_same_file_twice_keeps_one_set_of_chunks():
    service = make_service()
    first = service.ingest("security.txt", PASSWORD_DOC)
    count_after_first = service.store.count()

    second = service.ingest("security.txt", PASSWORD_DOC)

    assert first.status == "created" and second.status == "replaced"
    assert second.doc_id == first.doc_id
    assert service.store.count() == count_after_first
    assert len(service.store.list_documents()) == 1


def test_same_name_with_new_content_replaces_the_old_version():
    service = make_service()
    old = service.ingest("policy.txt", b"Annual leave is 18 days.")
    new = service.ingest("policy.txt", b"Annual leave is 24 days.")

    assert new.status == "updated" and new.doc_id != old.doc_id
    documents = service.store.list_documents()
    assert [doc["doc_id"] for doc in documents] == [new.doc_id]
    assert all("24 days" in chunk.text for chunk in service.store.all_chunks())
