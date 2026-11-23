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
