import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# post_report_to_pr.py reads REPO_SLUG/PR_NUMBER/COMMIT_SHA and a github token
# file at import time — real values only exist inside the in-cluster Job. The
# reporter fixture below sets fake env vars and mocks the token read before
# importing, so a plain `import integration_tests.post_report_to_pr` at
# collection time would otherwise crash every test in this file.
MODULE_PATH = (
    Path(__file__).parent.parent / "integration_tests" / "post_report_to_pr.py"
)


@pytest.fixture
def reporter(monkeypatch):
    monkeypatch.setenv("REPO_SLUG", "lukasb27/test-repo")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("COMMIT_SHA", "abc123")
    with patch("pathlib.Path.read_text", return_value="fake-token\n"):
        spec = importlib.util.spec_from_file_location("post_report_to_pr", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def fake_response(status_code, json_data):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def test_posts_new_comment_when_none_exists(reporter):
    with (
        patch.object(reporter.httpx, "get", return_value=fake_response(200, [])),
        patch.object(reporter.httpx, "post") as mock_post,
        patch.object(reporter.httpx, "patch") as mock_patch,
    ):
        reporter.post_comment(f"{reporter.COMMENT_MARKER}\nreport A")

    mock_post.assert_called_once()
    mock_patch.assert_not_called()
    assert mock_post.call_args.args[0].endswith("/issues/42/comments")


def test_updates_existing_comment_by_marker(reporter):
    existing = [
        {"id": 111, "body": "some unrelated comment"},
        {"id": 222, "body": f"{reporter.COMMENT_MARKER}\nold report B"},
    ]
    with (
        patch.object(reporter.httpx, "get", return_value=fake_response(200, existing)),
        patch.object(reporter.httpx, "post") as mock_post,
        patch.object(reporter.httpx, "patch") as mock_patch,
    ):
        reporter.post_comment(f"{reporter.COMMENT_MARKER}\nreport B updated")

    mock_patch.assert_called_once()
    mock_post.assert_not_called()
    assert mock_patch.call_args.args[0].endswith("/issues/comments/222")


def test_falls_back_to_new_comment_when_listing_fails(reporter):
    with (
        patch.object(reporter.httpx, "get", return_value=fake_response(403, {})),
        patch.object(reporter.httpx, "post") as mock_post,
        patch.object(reporter.httpx, "patch") as mock_patch,
    ):
        reporter.post_comment(f"{reporter.COMMENT_MARKER}\nreport C")

    mock_post.assert_called_once()
    mock_patch.assert_not_called()


def test_paginates_to_find_marker_on_later_page(reporter):
    page1 = [{"id": i, "body": f"noise {i}"} for i in range(100)]
    page2 = [{"id": 500, "body": f"{reporter.COMMENT_MARKER}\nreport D"}]

    def paged_get(*args, **kwargs):
        page = kwargs["params"]["page"]
        return fake_response(200, page1 if page == 1 else page2)

    with (
        patch.object(reporter.httpx, "get", side_effect=paged_get) as mock_get,
        patch.object(reporter.httpx, "post") as mock_post,
        patch.object(reporter.httpx, "patch") as mock_patch,
    ):
        reporter.post_comment(f"{reporter.COMMENT_MARKER}\nreport D updated")

    assert mock_get.call_count == 2
    mock_patch.assert_called_once()
    assert mock_patch.call_args.args[0].endswith("/issues/comments/500")
    mock_post.assert_not_called()


def test_unrelated_comment_without_marker_is_not_matched(reporter):
    existing = [{"id": 111, "body": "a totally unrelated comment"}]
    with (
        patch.object(reporter.httpx, "get", return_value=fake_response(200, existing)),
        patch.object(reporter.httpx, "post") as mock_post,
        patch.object(reporter.httpx, "patch") as mock_patch,
    ):
        reporter.post_comment(f"{reporter.COMMENT_MARKER}\nreport E")

    mock_post.assert_called_once()
    mock_patch.assert_not_called()
