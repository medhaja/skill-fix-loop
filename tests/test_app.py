import pytest
from fastapi.testclient import TestClient

from loop.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = tmp_path_factory.mktemp("reviews") / "reviews.jsonl"
    return TestClient(create_app(reviews_path=path, use_llm=False))


def test_pages_render(client):
    assert "deploy-preview" in client.get("/").text
    page = client.get("/skills/deploy-preview").text
    assert "Failure causes" in page and "Review edit" in page
    assert "Not affiliated with Nessie" in page
    assert "Candidate new skill" in client.get("/skills/write-migration").text
    assert "rule fired here" in client.get("/traces/" + _first_trace_link(page)).text
    assert "Simulated replay" in client.get("/results").text


def test_unknown_ids_404(client):
    assert client.get("/skills/nope").status_code == 404
    assert client.get("/proposals/nope").status_code == 404
    assert client.get("/traces/nope").status_code == 404


def test_approve_edit_and_reject_flow(client):
    pid = "deploy-preview-c1"
    page = client.get(f"/proposals/{pid}").text
    assert "Approve" in page and "Reject" in page

    r = client.post(f"/proposals/{pid}", data={"action": "approve", "diff": ""}, follow_redirects=False)
    assert r.status_code == 303
    results = client.get("/results").text
    assert "approved" in results and "missing_env_var" in results

    client.post(f"/proposals/{pid}", data={"action": "approve", "diff": "+- my own wording\n"})
    assert "edited" in client.get(f"/proposals/{pid}").text

    client.post(f"/proposals/{pid}", data={"action": "reject"})
    assert "none yet" in client.get("/results").text

    client.post("/results/reset")
    assert "No decisions yet" in client.get("/results").text


def _first_trace_link(html):
    start = html.index('href="/traces/') + len('href="/traces/')
    return html[start:html.index('"', start)]
