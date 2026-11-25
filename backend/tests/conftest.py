import pytest

from app.core.config import get_settings


@pytest.fixture(scope="session")
def dataset_dir():
    return get_settings().mira_dataset_dir


@pytest.fixture(scope="session")
def dataset():
    from app.data_loader import get_dataset
    return get_dataset()


@pytest.fixture(scope="session")
def rates(dataset):
    return dataset.rates


@pytest.fixture(scope="session")
def content(dataset):
    return dataset.content


def issue_codes(issues, code):
    """All issues with the given code."""
    return [i for i in issues if i.code == code]


@pytest.fixture(scope="session", autouse=True)
def dataset_only_library():
    """Tests see the dataset only: the app's startup must not add content items an approver
    published in the dev database (R8). test_content.py publishes into the library itself and
    restores it."""
    import app.main
    real = app.main.load_published
    app.main.load_published = lambda session: 0
    yield
    app.main.load_published = real


@pytest.fixture(autouse=True)
def gemini_provider_unless_asked(request, monkeypatch):
    """Offline tests are written against the Gemini model chain; a DEEPSEEK_API_KEY in .env must
    not change them. Tests marked `deepseek` (or `live`) see the real provider choice."""
    if request.node.get_closest_marker("deepseek") or request.node.get_closest_marker("live"):
        return
    from app.llm import client, structured
    monkeypatch.setattr(client, "provider", lambda: "gemini")
    monkeypatch.setattr(structured, "provider", lambda: "gemini")
