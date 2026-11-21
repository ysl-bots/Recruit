import base64

from recruit import publish


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise publish.requests.HTTPError(str(self.status_code))


def test_put_file_create_update_skip(monkeypatch):
    calls = []
    state = {"cur": R(404)}
    monkeypatch.setattr(publish.requests, "get", lambda url, **kw: state["cur"])
    monkeypatch.setattr(publish.requests, "put", lambda url, json, **kw: calls.append((url, json)) or R(201))
    assert publish.put_file("t", "o/r", "data/p.json", b"a", "m") is True
    assert "sha" not in calls[-1][1] and calls[-1][0].endswith("/repos/o/r/contents/data/p.json")
    state["cur"] = R(200, {"sha": "abc", "content": base64.b64encode(b"a").decode()})
    assert publish.put_file("t", "o/r", "data/p.json", b"a", "m") is False and len(calls) == 1
    assert publish.put_file("t", "o/r", "data/p.json", b"b", "m") is True and calls[-1][1]["sha"] == "abc"


def test_sync_public_reports_failures(tmp_path, monkeypatch):
    (tmp_path / "postings.json").write_text("{}")
    monkeypatch.setattr(publish, "put_file", lambda *a, **k: True)
    assert publish.sync_public("t", "o/r", tmp_path, ["postings.json", "missing.json"], "m") == ["missing.json"]
    assert publish.sync_public("", "o/r", tmp_path, ["postings.json"], "m") == ["postings.json"]
