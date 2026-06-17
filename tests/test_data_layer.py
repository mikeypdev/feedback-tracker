"""Tests for data-layer functions: load_feedback, create_item, filter, sort, etc."""

import shutil
from datetime import date, timedelta
from pathlib import Path

import frontmatter
import pytest

from src.tui import (
    CATEGORIES,
    PRIORITIES,
    STATUSES,
    append_note,
    compute_stats,
    create_item,
    delete_item,
    derive_enums,
    filter_items,
    increment_volume,
    load_feedback,
    next_id,
    quick_capture,
    slugify,
    sort_items,
)


@pytest.fixture
def fb_dir(tmp_path: Path) -> Path:
    d = tmp_path / "feedback"
    d.mkdir()
    return d


def _write_item(fb_dir: Path, item_id: int, slug: str, **overrides) -> Path:
    folder = fb_dir / f"{item_id:03d}-{slug}"
    folder.mkdir()
    meta = {
        "title": slug.replace("-", " ").title(),
        "category": "other",
        "priority": "medium",
        "status": "new",
        "source": "",
        "created": date.today().isoformat(),
        "tags": [],
        "volume": 1,
    }
    meta.update(overrides)
    post = frontmatter.Post("test body", **meta)
    frontmatter.dump(post, str(folder / "feedback.md"))
    return folder


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("What's the deal?! (fix)") == "whats-the-deal-fix"

    def test_multiple_spaces(self):
        assert slugify("a   b   c") == "a-b-c"

    def test_underscores(self):
        assert slugify("foo_bar_baz") == "foobarbaz"

    def test_leading_trailing(self):
        assert slugify("  --hello--  ") == "hello"

    def test_length_limit(self):
        long = "a" * 100
        assert len(slugify(long)) == 50

    def test_empty(self):
        assert slugify("") == ""


class TestNextId:
    def test_empty_dir(self, fb_dir: Path):
        assert next_id(fb_dir) == 1

    def test_nonexistent_dir(self, tmp_path: Path):
        assert next_id(tmp_path / "nope") == 1

    def test_with_items(self, fb_dir: Path):
        _write_item(fb_dir, 3, "c")
        _write_item(fb_dir, 1, "a")
        assert next_id(fb_dir) == 4

    def test_skips_non_dirs(self, fb_dir: Path):
        (fb_dir / "readme.txt").write_text("hi")
        _write_item(fb_dir, 1, "a")
        assert next_id(fb_dir) == 2


class TestLoadFeedback:
    def test_empty_dir(self, fb_dir: Path):
        assert load_feedback(fb_dir) == []

    def test_nonexistent_dir(self, tmp_path: Path):
        assert load_feedback(tmp_path / "nope") == []

    def test_loads_items(self, fb_dir: Path):
        _write_item(fb_dir, 1, "alpha", title="Alpha Item")
        _write_item(fb_dir, 2, "beta", title="Beta Item")
        items = load_feedback(fb_dir)
        assert len(items) == 2
        assert items[0]["id"] == 1
        assert items[1]["id"] == 2

    def test_skips_folders_without_md(self, fb_dir: Path):
        (fb_dir / "003-no-md").mkdir()
        _write_item(fb_dir, 1, "alpha")
        assert len(load_feedback(fb_dir)) == 1

    def test_skips_non_pattern_folders(self, fb_dir: Path):
        (fb_dir / "notes").mkdir()
        (fb_dir / "notes" / "feedback.md").write_text("---\ntitle: x\n---\n")
        _write_item(fb_dir, 1, "alpha")
        assert len(load_feedback(fb_dir)) == 1

    def test_stale_detection(self, fb_dir: Path):
        old = (date.today() - timedelta(days=10)).isoformat()
        _write_item(fb_dir, 1, "old", status="new", created=old)
        _write_item(fb_dir, 2, "fresh", status="new", created=date.today().isoformat())
        items = load_feedback(fb_dir)
        assert items[0]["stale"] is True
        assert items[1]["stale"] is False

    def test_not_stale_if_not_new(self, fb_dir: Path):
        old = (date.today() - timedelta(days=30)).isoformat()
        _write_item(fb_dir, 1, "old-triaged", status="triaged", created=old)
        items = load_feedback(fb_dir)
        assert items[0]["stale"] is False

    def test_defaults(self, fb_dir: Path):
        folder = fb_dir / "001-test"
        folder.mkdir()
        md = folder / "feedback.md"
        md.write_text("---\ntitle: Test\n---\nbody text\n")
        items = load_feedback(fb_dir)
        assert len(items) == 1
        assert items[0]["category"] == "other"
        assert items[0]["priority"] == "medium"
        assert items[0]["status"] == "new"
        assert items[0]["volume"] == 1
        assert items[0].get("version") == ""
        assert items[0]["body"] == "body text"

    def test_sorted_by_folder_name(self, fb_dir: Path):
        _write_item(fb_dir, 3, "zeta")
        _write_item(fb_dir, 1, "alpha")
        _write_item(fb_dir, 2, "middle")
        items = load_feedback(fb_dir)
        assert [i["id"] for i in items] == [1, 2, 3]


class TestCreateItem:
    def test_creates_folder_and_file(self, fb_dir: Path):
        folder = create_item(fb_dir, "Test Item")
        assert folder.exists()
        assert (folder / "feedback.md").exists()

    def test_folder_naming(self, fb_dir: Path):
        folder = create_item(fb_dir, "My Bug")
        assert folder.name == "001-my-bug"

    def test_increments_id(self, fb_dir: Path):
        create_item(fb_dir, "First")
        folder = create_item(fb_dir, "Second")
        assert folder.name.startswith("002-")

    def test_frontmatter_defaults(self, fb_dir: Path):
        create_item(fb_dir, "Check FM")
        items = load_feedback(fb_dir)
        assert items[0]["title"] == "Check FM"
        assert items[0]["status"] == "new"
        assert items[0]["priority"] == "medium"
        assert items[0]["category"] == "other"
        assert items[0]["created"] == date.today().isoformat()


class TestQuickCapture:
    def test_creates_item(self, fb_dir: Path):
        folder = quick_capture(fb_dir, "Quick Note")
        assert folder.exists()
        items = load_feedback(fb_dir)
        assert len(items) == 1
        assert items[0]["title"] == "Quick Note"


class TestAppendNote:
    def test_appends_dated_note(self, fb_dir: Path):
        folder = _write_item(fb_dir, 1, "test")
        append_note(folder, "observed this today")
        content = (folder / "feedback.md").read_text()
        today = date.today().isoformat()
        assert f"### {today}" in content
        assert "observed this today" in content

    def test_missing_file(self, fb_dir: Path):
        folder = fb_dir / "001-nope"
        folder.mkdir()
        append_note(folder, "text")

    def test_multiple_notes(self, fb_dir: Path):
        folder = _write_item(fb_dir, 1, "test")
        append_note(folder, "first note")
        append_note(folder, "second note")
        content = (folder / "feedback.md").read_text()
        assert content.count(f"### {date.today().isoformat()}") == 2


class TestIncrementVolume:
    def test_increments(self, fb_dir: Path):
        _write_item(fb_dir, 1, "test", volume=3)
        increment_volume(fb_dir / "001-test")
        items = load_feedback(fb_dir)
        assert items[0]["volume"] == 4

    def test_missing_file(self, fb_dir: Path):
        folder = fb_dir / "001-nope"
        folder.mkdir()
        increment_volume(folder)


class TestDeleteItem:
    def test_deletes_folder(self, fb_dir: Path):
        folder = _write_item(fb_dir, 1, "test")
        delete_item(folder)
        assert not folder.exists()

    def test_idempotent(self, fb_dir: Path):
        folder = fb_dir / "001-ghost"
        delete_item(folder)


class TestComputeStats:
    def _make_item(self, **overrides):
        defaults = {"status": "new", "priority": "medium"}
        defaults.update(overrides)
        return defaults

    def test_empty(self):
        assert compute_stats([]) == {"total": 0, "new": 0, "high": 0, "critical": 0}

    def test_mixed(self):
        items = [
            self._make_item(status="new", priority="critical"),
            self._make_item(status="new", priority="high"),
            self._make_item(status="triaged", priority="low"),
        ]
        stats = compute_stats(items)
        assert stats["total"] == 3
        assert stats["new"] == 2
        assert stats["high"] == 2
        assert stats["critical"] == 1


class TestFilterItems:
    def _items(self):
        return [
            {"title": "A", "body": "alpha content", "category": "difficulty", "priority": "high", "status": "new"},
            {"title": "B", "body": "beta stuff", "category": "fun", "priority": "low", "status": "triaged"},
            {"title": "C", "body": "gamma", "category": "difficulty", "priority": "medium", "status": "new"},
        ]

    def test_no_filters(self):
        assert len(filter_items(self._items())) == 3

    def test_category(self):
        result = filter_items(self._items(), category="difficulty")
        assert len(result) == 2

    def test_priority(self):
        result = filter_items(self._items(), priority="high")
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_status(self):
        result = filter_items(self._items(), status="new")
        assert len(result) == 2

    def test_query_title(self):
        result = filter_items(self._items(), query="beta")
        assert len(result) == 1

    def test_query_body(self):
        result = filter_items(self._items(), query="alpha content")
        assert len(result) == 1

    def test_combined(self):
        result = filter_items(self._items(), category="difficulty", status="new")
        assert len(result) == 2

    def test_no_match(self):
        result = filter_items(self._items(), category="audio")
        assert len(result) == 0


class TestSortItems:
    def _items(self):
        return [
            {"id": 1, "volume": 5, "priority": "low", "status": "new", "category": "a", "title": "Zebra"},
            {"id": 2, "volume": 10, "priority": "critical", "status": "triaged", "category": "b", "title": "Apple"},
            {"id": 3, "volume": 1, "priority": "high", "status": "addressed", "category": "c", "title": "Mango"},
        ]

    def test_sort_id(self):
        ids = [i["id"] for i in sort_items(self._items(), "id")]
        assert ids == [1, 2, 3]

    def test_sort_volume_desc(self):
        vols = [i["volume"] for i in sort_items(self._items(), "volume", reverse=True)]
        assert vols == [10, 5, 1]

    def test_sort_priority(self):
        pris = [i["priority"] for i in sort_items(self._items(), "priority")]
        assert pris == ["critical", "high", "low"]

    def test_sort_status(self):
        statuses = [i["status"] for i in sort_items(self._items(), "status")]
        assert statuses == ["new", "triaged", "addressed"]

    def test_sort_title(self):
        titles = [i["title"] for i in sort_items(self._items(), "title")]
        assert titles == ["Apple", "Mango", "Zebra"]


    def test_sort_version(self):
        items = [
            {"id": 1, "volume": 5, "version": 3, "priority": "low", "status": "new", "category": "a", "title": "Zebra"},
            {"id": 2, "volume": 10, "version": 1, "priority": "critical", "status": "triaged", "category": "b", "title": "Apple"},
            {"id": 3, "volume": 1, "version": 5, "priority": "high", "status": "addressed", "category": "c", "title": "Mango"},
        ]
        vers = [i['version'] for i in sort_items(items, 'version')]
        assert vers == [1, 3, 5]


class TestFrontmatterRoundTrip:
    def test_dump_and_reload_preserves_all_fields(self, fb_dir: Path):
        _write_item(fb_dir, 1, "round-trip", **{
            "title": "Round Trip Test",
            "category": "gameplay",
            "priority": "high",
            "status": "in-progress",
            "source": "Discord",
            "tags": ["a", "b"],
            "volume": 7,
        })
        items = load_feedback(fb_dir)
        assert len(items) == 1
        item = items[0]
        assert item["title"] == "Round Trip Test"
        assert item["category"] == "gameplay"
        assert item["priority"] == "high"
        assert item["status"] == "in-progress"
        assert item["source"] == "Discord"
        assert item["tags"] == ["a", "b"]
        assert item["volume"] == 7

    def test_increment_volume_preserves_other_fields(self, fb_dir: Path):
        _write_item(fb_dir, 1, "vol-test", **{
            "title": "Vol Test",
            "tags": ["x"],
            "source": "Reddit",
            "volume": 3,
        })
        increment_volume(fb_dir / "001-vol-test")
        items = load_feedback(fb_dir)
        assert items[0]["volume"] == 4
        assert items[0]["tags"] == ["x"]
        assert items[0]["source"] == "Reddit"
        assert items[0]["title"] == "Vol Test"


class TestDeriveEnums:
    def _item(self, category="other", priority="medium", status="new", **kw):
        return {"category": category, "priority": priority, "status": status, **kw}

    def test_empty_returns_defaults(self):
        cats, pris, stats = derive_enums([])
        assert cats == CATEGORIES
        assert pris == PRIORITIES
        assert stats == STATUSES

    def test_derives_from_items(self):
        items = [
            self._item(category="alpha", priority="low", status="new"),
            self._item(category="beta", priority="high", status="done"),
        ]
        cats, pris, stats = derive_enums(items)
        assert cats == ["alpha", "beta"]
        assert pris == ["high", "low"]
        assert stats == ["new", "done"]

    def test_deduplicates(self):
        items = [
            self._item(category="x"),
            self._item(category="x"),
            self._item(category="y"),
        ]
        cats, _, _ = derive_enums(items)
        assert cats == ["x", "y"]

    def test_priority_sort_order(self):
        items = [
            self._item(priority="low"),
            self._item(priority="critical"),
            self._item(priority="medium"),
        ]
        _, pris, _ = derive_enums(items)
        assert pris == ["critical", "medium", "low"]

    def test_custom_values(self):
        items = [
            self._item(category="performance", priority="urgent", status="investigating"),
        ]
        cats, pris, stats = derive_enums(items)
        assert cats == ["performance"]
        assert pris == ["urgent"]
        assert stats == ["investigating"]
