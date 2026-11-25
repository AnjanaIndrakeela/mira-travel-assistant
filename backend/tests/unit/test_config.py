from datetime import date

from app.core.config import Settings


def test_default_today_is_eval_date():
    assert Settings(_env_file=None).mira_today == date(2026, 11, 19)


def test_today_is_configurable(monkeypatch):
    monkeypatch.setenv("MIRA_TODAY", "2027-01-05")
    assert Settings(_env_file=None).mira_today == date(2027, 1, 5)


def test_dataset_dir_exists():
    s = Settings(_env_file=None)
    assert (s.mira_dataset_dir / "rates" / "rate_sheet_2026-27.xlsx").is_file()


def test_api_key_is_hidden_when_printed():
    s = Settings(_env_file=None, gemini_api_key="super-secret-value")
    assert "super-secret-value" not in repr(s)
    assert "super-secret-value" not in str(s.model_dump())
    assert s.gemini_api_key.get_secret_value() == "super-secret-value"


def test_empty_api_key_means_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert Settings(_env_file=None).gemini_api_key is None


def test_empty_margin_override_means_none(monkeypatch):
    monkeypatch.setenv("MIRA_MARGIN_DAY", "")
    assert Settings(_env_file=None).mira_margin_day is None
