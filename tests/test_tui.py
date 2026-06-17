"""Tests for the Textual TUI app — mounting, keybindings, filters, sort, CRUD."""

import pytest
import pytest_asyncio
from pathlib import Path
from datetime import date, timedelta
from textual.widgets import DataTable, Input

from src.tui import (
    CATEGORIES,
    PRIORITIES,
    STATUSES,
    DetailPane,
    FeedbackApp,
    load_feedback,
)
import frontmatter


def _write_item(fb_dir: Path, item_id: int, slug: str, **overrides) -> Path:
    folder = fb_dir / f"{item_id:03d}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
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


@pytest.fixture
def fb_dir(tmp_path: Path) -> Path:
    d = tmp_path / "feedback"
    d.mkdir()
    _write_item(d, 1, "alpha-item", title="Alpha", category="difficulty",
                priority="high", status="triaged", volume=5)
    _write_item(d, 2, "beta-item", title="Beta", category="fun",
                priority="low", status="new", volume=1)
    _write_item(d, 3, "gamma-item", title="Gamma", category="gameplay",
                priority="medium", status="planned", volume=3)
    return d


@pytest_asyncio.fixture
async def app(fb_dir: Path):
    a = FeedbackApp(fb_dir)
    async with a.run_test(size=(120, 30)) as pilot:
        yield a, pilot


def _row_count(app: FeedbackApp) -> int:
    return app.query_one("#table", DataTable).row_count


def _selected(app: FeedbackApp) -> dict | None:
    return app._get_selected_item()


class TestAppMount:
    @pytest.mark.asyncio
    async def test_mounts_with_items(self, app):
        a, pilot = app
        assert _row_count(a) == 3

    @pytest.mark.asyncio
    async def test_detail_shows_selected(self, app):
        a, pilot = app
        item = _selected(a)
        assert item is not None
        assert item["id"] == 1

    @pytest.mark.asyncio
    async def test_detail_pane_content(self, app):
        a, pilot = app
        detail = a.query_one("#detail-pane", DetailPane)
        assert detail is not None


class TestNavigation:
    @pytest.mark.asyncio
    async def test_j_moves_down(self, app):
        a, pilot = app
        await pilot.press("down")
        await pilot.pause()
        assert _selected(a)["id"] == 2

    @pytest.mark.asyncio
    async def test_k_moves_up(self, app):
        a, pilot = app
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert _selected(a)["id"] == 1

    @pytest.mark.asyncio
    async def test_k_at_top_stays(self, app):
        a, pilot = app
        await pilot.press("up")
        await pilot.pause()
        assert _selected(a)["id"] == 1


class TestCategoryFilter:
    @pytest.mark.asyncio
    async def test_cycle_forward(self, app):
        a, pilot = app
        await pilot.press("c")
        await pilot.pause()
        assert a.filter_category == "difficulty"
        assert _row_count(a) == 1

    @pytest.mark.asyncio
    async def test_cycle_through_all(self, app):
        a, pilot = app
        expected_cats = sorted({"difficulty", "fun", "gameplay"})
        for cat in expected_cats:
            await pilot.press("c")
            await pilot.pause()
            assert a.filter_category == cat
        await pilot.press("c")
        await pilot.pause()
        assert a.filter_category is None
        assert _row_count(a) == 3

    @pytest.mark.asyncio
    async def test_clear_resets(self, app):
        a, pilot = app
        await pilot.press("c")
        await pilot.pause()
        assert a.filter_category is not None
        await pilot.press("x")
        await pilot.pause()
        assert a.filter_category is None
        assert _row_count(a) == 3


class TestPriorityFilter:
    @pytest.mark.asyncio
    async def test_cycle(self, app):
        a, pilot = app
        # Priorities in data: high(1), low(3), medium(2) — sorted by PRIORITY_SORT
        await pilot.press("p")
        await pilot.pause()
        assert a.filter_priority == "high"
        assert _row_count(a) == 1

        await pilot.press("p")
        await pilot.pause()
        assert a.filter_priority == "medium"


class TestStatusFilter:
    @pytest.mark.asyncio
    async def test_cycle(self, app):
        a, pilot = app
        await pilot.press("s")
        await pilot.pause()
        assert a.filter_status == "new"
        assert _row_count(a) == 1

        await pilot.press("s")
        await pilot.pause()
        assert a.filter_status == "triaged"
        assert _row_count(a) == 1


class TestClearFilters:
    @pytest.mark.asyncio
    async def test_clears_all(self, app):
        a, pilot = app
        await pilot.press("c")
        await pilot.press("p")
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert a.filter_category is None
        assert a.filter_priority is None
        assert a.filter_status is None
        assert a.search_query == ""
        assert _row_count(a) == 3


class TestSort:
    @pytest.mark.asyncio
    async def test_tab_cycles_sort_column(self, app):
        a, pilot = app
        assert a.sort_col == "id"
        await pilot.press("tab")
        await pilot.pause()
        assert a.sort_col == "volume"
        await pilot.press("tab")
        await pilot.pause()
        assert a.sort_col == "version"
        await pilot.press("tab")
        await pilot.pause()
        assert a.sort_col == "priority"

    @pytest.mark.asyncio
    async def test_sort_affects_order(self, app):
        a, pilot = app
        await pilot.press("tab")
        await pilot.pause()
        assert a.sort_col == "volume"
        # volume sort ascending: item 2 (vol=1) first
        assert _selected(a)["id"] == 2


class TestVolumeBump:
    @pytest.mark.asyncio
    async def test_bumps_volume(self, app):
        a, pilot = app
        item = _selected(a)
        assert item["id"] == 1
        old_vol = item["volume"]

        await pilot.press("v")
        await pilot.pause()

        items = load_feedback(a.feedback_dir)
        item1 = [i for i in items if i["id"] == 1][0]
        assert item1["volume"] == old_vol + 1


class TestQuickCapture:
    @pytest.mark.asyncio
    async def test_quick_capture_creates_item(self, app):
        a, pilot = app
        assert _row_count(a) == 3

        await pilot.press("shift+n")
        await pilot.pause()

        search = a.query_one("#search-input", Input)
        assert a._input_mode == "quick"

        await pilot.press("T")
        await pilot.press("e")
        await pilot.press("s")
        await pilot.press("t")
        await pilot.press("enter")
        await pilot.pause()

        assert a._input_mode == "search"
        assert _row_count(a) == 4

        items = load_feedback(a.feedback_dir)
        titles = [i["title"] for i in items]
        assert "Test" in titles


class TestAddNote:
    @pytest.mark.asyncio
    async def test_add_note_appends(self, app):
        a, pilot = app
        item = _selected(a)
        assert item is not None

        await pilot.press("plus")
        await pilot.pause()
        assert a._input_mode == "note"

        await pilot.press("o")
        await pilot.press("b")
        await pilot.press("s")
        await pilot.press("enter")
        await pilot.pause()

        assert a._input_mode == "search"
        items = load_feedback(a.feedback_dir)
        target = [i for i in items if i["id"] == item["id"]][0]
        today = date.today().isoformat()
        assert f"### {today}" in target["body"]
        assert "obs" in target["body"]


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_confirmed(self, app):
        a, pilot = app
        assert _row_count(a) == 3

        await pilot.press("d")
        await pilot.pause(0.3)

        await pilot.press("y")
        await pilot.pause(0.3)

        assert _row_count(a) == 2
        remaining_ids = [i["id"] for i in load_feedback(a.feedback_dir)]
        assert 1 not in remaining_ids

    @pytest.mark.asyncio
    async def test_delete_denied(self, app):
        a, pilot = app
        assert _row_count(a) == 3

        await pilot.press("d")
        await pilot.pause(0.3)

        await pilot.press("n")
        await pilot.pause(0.3)

        assert _row_count(a) == 3


class TestSearchInput:
    @pytest.mark.asyncio
    async def test_focus_search(self, app):
        a, pilot = app
        search = a.query_one("#search-input", Input)
        await pilot.press("slash")
        await pilot.pause()
        assert search.has_focus

    @pytest.mark.asyncio
    async def test_search_filters_live(self, app):
        a, pilot = app
        await pilot.press("slash")
        await pilot.pause()
        search = a.query_one("#search-input", Input)
        await pilot.press("a")
        await pilot.press("l")
        await pilot.press("p")
        await pilot.press("h")
        await pilot.press("a")
        await pilot.pause()
        assert _row_count(a) == 1


class TestReload:
    @pytest.mark.asyncio
    async def test_reload_picks_up_new_files(self, app):
        a, pilot = app
        assert _row_count(a) == 3
        _write_item(a.feedback_dir, 4, "new-from-disk", title="Disk Item")
        a._reload()
        await pilot.pause()
        assert _row_count(a) == 4

    @pytest.mark.asyncio
    async def test_reload_removes_deleted_files(self, app):
        a, pilot = app
        assert _row_count(a) == 3
        import shutil
        shutil.rmtree(a.feedback_dir / "001-alpha-item")
        a._reload()
        await pilot.pause()
        assert _row_count(a) == 2


class TestStaleMarker:
    @pytest.mark.asyncio
    async def test_stale_item_shows_warning(self, tmp_path: Path):
        fb = tmp_path / "feedback"
        fb.mkdir()
        old = (date.today() - timedelta(days=10)).isoformat()
        _write_item(fb, 1, "stale-one", status="new", created=old)
        _write_item(fb, 2, "fresh-one", status="new", created=date.today().isoformat())

        a = FeedbackApp(fb)
        async with a.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            items = load_feedback(fb)
            assert items[0]["stale"] is True
            assert items[1]["stale"] is False
