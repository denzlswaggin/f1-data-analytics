from pathlib import Path

PAGES_DIR = Path(__file__).parents[1] / "dashboard" / "pages"


def test_all_dashboard_pages_use_the_wide_layout() -> None:
    pages = sorted(PAGES_DIR.glob("*.md"))

    assert pages
    for page in pages:
        frontmatter = page.read_text(encoding="utf-8").split("---", 2)[1]
        assert "max_width: 1600" in frontmatter, page.name
