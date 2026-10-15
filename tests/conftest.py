import pytest
import requests


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Tests must not contact external services")

    monkeypatch.setattr(requests.Session, "get", fail)
