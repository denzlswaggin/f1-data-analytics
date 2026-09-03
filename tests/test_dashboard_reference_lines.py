from pathlib import Path


PAGES_DIR = Path(__file__).parents[1] / "dashboard" / "pages"


def test_saturday_vs_sunday_diagonal_has_two_endpoints() -> None:
    content = (PAGES_DIR / "saturday-vs-sunday.md").read_text(encoding="utf-8")

    assert "min(least(quali_rating, race_rating)) as x1" in content
    assert "max(greatest(quali_rating, race_rating)) as x2" in content
    assert "x=x1" in content
    assert "y=y1" in content
    assert "x2=x2" in content
    assert "y2=y2" in content
