from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

HTML = Path(__file__).resolve().parents[1] / "fixtures" / "html"


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/browser" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.browser)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    yield page
    context.close()


def load_fixture(page: Page, name: str) -> None:
    page.set_content((HTML / name).read_text(encoding="utf-8"))
    page.wait_for_timeout(100)  # let the inline script attach the shadow root and iframe
