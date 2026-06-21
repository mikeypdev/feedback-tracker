#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import frontmatter
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Static

CATEGORIES = [
    "difficulty", "gameplay", "fun", "understanding",
    "narrative", "visual", "audio", "ux", "other",
]
PRIORITIES = ["critical", "high", "medium", "low"]
STATUSES = ["new", "triaged", "planned", "in-progress", "addressed", "wontfix", "duplicate"]

PRIORITY_SORT = {p: i for i, p in enumerate(PRIORITIES)}
STATUS_ORDER = {s: i for i, s in enumerate(STATUSES)}


def derive_enums(items: list[dict]) -> tuple[list[str], list[str], list[str]]:
    cats = sorted({i["category"] for i in items if i.get("category")}) or CATEGORIES
    pris = sorted({i["priority"] for i in items if i.get("priority")}, key=lambda p: PRIORITY_SORT.get(p, 99)) or PRIORITIES
    stats = sorted({i["status"] for i in items if i.get("status")}, key=lambda s: STATUS_ORDER.get(s, 99)) or STATUSES
    return cats, pris, stats

TEMPLATE = """---
title: "{title}"
category: other
priority: medium
status: new
source: ""
created: "{today}"
tags: []
volume: 1
version: ""
---

"""


def load_feedback(feedback_dir: Path) -> list[dict]:
    items = []
    if not feedback_dir.exists():
        return items
    for folder in sorted(feedback_dir.iterdir()):
        if not folder.is_dir():
            continue
        md_path = folder / "feedback.md"
        if not md_path.exists():
            continue
        try:
            post = frontmatter.load(str(md_path))
        except Exception:
            continue
        name = folder.name
        match = re.match(r"^(\d+)-(.+)$", name)
        if not match:
            continue
        item_id = int(match.group(1))
        slug = match.group(2)
        meta = post.metadata
        stat = meta.get("status", "new")
        created_str = meta.get("created", "")
        created_date = None
        try:
            created_date = datetime.strptime(str(created_str), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
        stale = False
        if stat == "new" and created_date:
            stale = (date.today() - created_date).days > 7
        items.append({
            "id": item_id,
            "slug": slug,
            "path": folder,
            "md_path": md_path,
            "title": meta.get("title", slug),
            "category": meta.get("category", "other"),
            "priority": meta.get("priority", "medium"),
            "status": stat,
            "source": meta.get("source", ""),
            "created": created_str,
            "tags": meta.get("tags", []),
            "volume": meta.get("volume", 1),
            "version": meta.get("version", ""),
            "body": post.content,
            "stale": stale,
            "mtime": md_path.stat().st_mtime,
        })
    return items


def next_id(feedback_dir: Path) -> int:
    if not feedback_dir.exists():
        return 1
    max_id = 0
    for folder in feedback_dir.iterdir():
        if not folder.is_dir():
            continue
        match = re.match(r"^(\d+)-", folder.name)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max_id + 1


def slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:50]


def create_item(feedback_dir: Path, title: str) -> Path:
    feedback_dir.mkdir(parents=True, exist_ok=True)
    item_id = next_id(feedback_dir)
    slug = slugify(title)
    folder = feedback_dir / f"{item_id:03d}-{slug}"
    folder.mkdir()
    md_path = folder / "feedback.md"
    content = TEMPLATE.format(title=title, today=date.today().isoformat())
    md_path.write_text(content)
    return folder


def quick_capture(feedback_dir: Path, title: str) -> Path:
    folder = create_item(feedback_dir, title)
    post = frontmatter.load(str(folder / "feedback.md"))
    post.metadata["title"] = title
    frontmatter.dump(post, str(folder / "feedback.md"))
    return folder


def append_note(item_path: Path, text: str) -> None:
    md_path = item_path / "feedback.md"
    if not md_path.exists():
        return
    content = md_path.read_text()
    today = date.today().isoformat()
    content = content.rstrip("\n") + f"\n\n### {today}\n{text}\n"
    md_path.write_text(content)


def increment_volume(item_path: Path) -> None:
    md_path = item_path / "feedback.md"
    if not md_path.exists():
        return
    post = frontmatter.load(str(md_path))
    post.metadata["volume"] = post.metadata.get("volume", 1) + 1
    frontmatter.dump(post, str(md_path))


def compute_stats(items: list[dict]) -> dict:
    return {
        "total": len(items),
        "new": sum(1 for i in items if i["status"] == "new"),
        "high": sum(1 for i in items if i["priority"] in ("high", "critical")),
        "critical": sum(1 for i in items if i["priority"] == "critical"),
    }


def delete_item(item_path: Path) -> None:
    if item_path.exists():
        shutil.rmtree(item_path)


def open_editor(path: Path) -> None:
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(path)])


def open_viewer(path: Path) -> None:
    cmd = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([cmd, str(path)])


def filter_items(
    items: list[dict],
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    query: str = "",
) -> list[dict]:
    result = items
    if category:
        result = [i for i in result if i["category"] == category]
    if priority:
        result = [i for i in result if i["priority"] == priority]
    if status:
        result = [i for i in result if i["status"] == status]
    if query:
        q = query.lower()
        result = [i for i in result if q in i["title"].lower() or q in i["body"].lower()]
    return result


SORT_COLUMNS = ["id", "volume", "version", "priority", "status", "category", "title"]


def sort_items(items: list[dict], column: str, reverse: bool = False) -> list[dict]:
    key_funcs = {
        "id": lambda i: i["id"],
        "volume": lambda i: i["volume"],
        "version": lambda i: i.get("version") or 0,
        "priority": lambda i: PRIORITY_SORT.get(i["priority"], 99),
        "status": lambda i: STATUS_ORDER.get(i["status"], 99),
        "category": lambda i: i["category"],
        "title": lambda i: i["title"].lower(),
    }
    return sorted(items, key=key_funcs.get(column, lambda i: i["id"]), reverse=reverse)


class DetailPane(Static):
    def show_item(self, item: dict | None) -> None:
        if item is None:
            self.update("")
            return
        title = item["title"]
        stale_marker = " ⚠" if item.get("stale") else ""
        lines = [
            f"[bold]#{item['id']}[/]: {title}{stale_marker}",
            "",
            f"  Category: [cyan]{item['category']}[/]",
            f"  Priority: [yellow]{item['priority']}[/]",
            f"  Status:   [green]{item['status']}[/]",
            f"  Volume:   {item['volume']}",
        ]
        if item.get("version"):
            lines.append(f"  Version:  {item['version']}")
        if item.get("source"):
            lines.append(f"  Source:   {item['source']}")
        if item.get("tags"):
            lines.append(f"  Tags:     {', '.join(item['tags'])}")
        lines.append("")
        body = item.get("body", "").strip()
        if body:
            lines.append(body)
        self.update("\n".join(lines))


class FeedbackApp(App):
    CSS = """
    #main-container {
        layout: horizontal;
        height: 1fr;
    }
    #list-pane {
        width: 2fr;
        height: 1fr;
    }
    #detail-pane {
        width: 1fr;
        height: 1fr;
        border-left: solid $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    #filter-bar {
        height: 3;
        padding: 0 1;
    }
    #filter-bar Input {
        width: 1fr;
    }
    #stats-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("o", "open_viewer", "Open"),
        Binding("q", "quit", "Quit"),
        Binding("n", "new_item", "New"),
        Binding("shift+n", "quick_capture", "Quick", key_display="N"),
        Binding("e", "edit_item", "Edit"),
        Binding("plus", "add_note", "+Note"),
        Binding("d", "delete_item", "Delete"),
        Binding("v", "bump_volume", "Volume"),
        Binding("slash", "focus_search", "Search"),
        Binding("c", "cycle_category", "Category"),
        Binding("p", "cycle_priority", "Priority"),
        Binding("s", "cycle_status", "Status"),
        Binding("x", "clear_filters", "Clear"),
        Binding("tab", "cycle_sort", "Sort", priority=True),
        Binding("question_mark", "show_help", "Help", key_display="?"),
    ]

    def __init__(self, feedback_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.feedback_dir = feedback_dir
        self.items: list[dict] = []
        self.filtered: list[dict] = []
        self.filter_category: str | None = None
        self.filter_priority: str | None = None
        self.filter_status: str | None = None
        self.search_query: str = ""
        self.sort_col: str = "id"
        self.sort_reverse: bool = False
        self._input_mode: str = "search"  # "search" | "quick" | "note"
        self._note_target: dict | None = None
        self.categories: list[str] = list(CATEGORIES)
        self.priorities: list[str] = list(PRIORITIES)
        self.statuses: list[str] = list(STATUSES)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Input(placeholder="[/] search...", id="search-input"),
            id="filter-bar",
        )
        with Horizontal(id="main-container"):
            with Vertical(id="list-pane"):
                yield DataTable(id="table")
            yield DetailPane(id="detail-pane")
        yield Static(id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Vol", "Ver", "Pri", "Status", "Category", "Title")
        table.focus()
        self._reload()

    def _reload(self) -> None:
        self.items = load_feedback(self.feedback_dir)
        self.categories, self.priorities, self.statuses = derive_enums(self.items)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self.filtered = filter_items(
            self.items,
            category=self.filter_category,
            priority=self.filter_priority,
            status=self.filter_status,
            query=self.search_query,
        )
        self.filtered = sort_items(self.filtered, self.sort_col, self.sort_reverse)
        self._populate_table()
        self._update_stats()
        self._show_detail()

    def _populate_table(self) -> None:
        table = self.query_one("#table", DataTable)
        cursor_row = table.cursor_row
        table.clear()
        for item in self.filtered:
            stale = " ⚠" if item.get("stale") else ""
            table.add_row(
                str(item["id"]),
                str(item["volume"]),
                str(item["version"]) if item.get("version") else "",
                item["priority"].upper(),
                item["status"],
                item["category"],
                item["title"] + stale,
                key=str(item["id"]),
            )
        if self.filtered and cursor_row < len(self.filtered):
            table.move_cursor(row=cursor_row)
        elif self.filtered:
            table.move_cursor(row=len(self.filtered) - 1)

    def _update_stats(self) -> None:
        stats = compute_stats(self.filtered)
        bar = self.query_one("#stats-bar", Static)
        parts = [f"{stats['total']} items"]
        if stats["new"]:
            parts.append(f"{stats['new']} new")
        if stats["high"]:
            parts.append(f"{stats['high']} high")
        if stats["critical"]:
            parts.append(f"{stats['critical']} critical")

        filter_parts = []
        if self.filter_category:
            filter_parts.append(f"cat={self.filter_category}")
        if self.filter_priority:
            filter_parts.append(f"pri={self.filter_priority}")
        if self.filter_status:
            filter_parts.append(f"status={self.filter_status}")
        if self.search_query:
            filter_parts.append(f"q={self.search_query}")
        sort_info = f"sort={self.sort_col}{'↓' if self.sort_reverse else '↑'}"

        line = " · ".join(parts)
        if filter_parts:
            line += "  │  filters: " + " ".join(filter_parts)
        line += f"  │  {sort_info}"
        bar.update(line)

    def _get_selected_item(self) -> dict | None:
        table = self.query_one("#table", DataTable)
        if not self.filtered or table.cursor_row >= len(self.filtered):
            return None
        return self.filtered[table.cursor_row]

    def _show_detail(self) -> None:
        detail = self.query_one("#detail-pane", DetailPane)
        item = self._get_selected_item()
        detail.show_item(item)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_detail()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input" and self._input_mode == "search":
            self.search_query = event.value
            self._apply_filters()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        if self._input_mode == "quick":
            title = event.value.strip()
            if title:
                quick_capture(self.feedback_dir, title)
                event.input.value = ""
                self._reload()
            self._input_mode = "search"
            event.input.placeholder = "[/] search..."
            self.query_one("#table", DataTable).focus()
        elif self._input_mode == "note":
            text = event.value.strip()
            if text and self._note_target:
                append_note(self._note_target["path"], text)
                event.input.value = ""
            self._input_mode = "search"
            self._note_target = None
            event.input.placeholder = "[/] search..."
            self._reload()
            self.query_one("#table", DataTable).focus()
        else:
            self.query_one("#table", DataTable).focus()

    def action_focus_search(self) -> None:
        search = self.query_one("#search-input", Input)
        search.focus()

    def action_cycle_category(self) -> None:
        if not self.categories:
            return
        if self.filter_category is None:
            self.filter_category = self.categories[0]
        elif self.filter_category not in self.categories:
            self.filter_category = self.categories[0]
        else:
            idx = self.categories.index(self.filter_category)
            if idx + 1 >= len(self.categories):
                self.filter_category = None
            else:
                self.filter_category = self.categories[idx + 1]
        self._apply_filters()

    def action_cycle_priority(self) -> None:
        if not self.priorities:
            return
        if self.filter_priority is None:
            self.filter_priority = self.priorities[0]
        elif self.filter_priority not in self.priorities:
            self.filter_priority = self.priorities[0]
        else:
            idx = self.priorities.index(self.filter_priority)
            if idx + 1 >= len(self.priorities):
                self.filter_priority = None
            else:
                self.filter_priority = self.priorities[idx + 1]
        self._apply_filters()

    def action_cycle_status(self) -> None:
        if not self.statuses:
            return
        if self.filter_status is None:
            self.filter_status = self.statuses[0]
        elif self.filter_status not in self.statuses:
            self.filter_status = self.statuses[0]
        else:
            idx = self.statuses.index(self.filter_status)
            if idx + 1 >= len(self.statuses):
                self.filter_status = None
            else:
                self.filter_status = self.statuses[idx + 1]
        self._apply_filters()

    def action_clear_filters(self) -> None:
        self.filter_category = None
        self.filter_priority = None
        self.filter_status = None
        self.search_query = ""
        search = self.query_one("#search-input", Input)
        search.value = ""
        self._apply_filters()

    def action_cycle_sort(self) -> None:
        idx = SORT_COLUMNS.index(self.sort_col)
        next_idx = (idx + 1) % len(SORT_COLUMNS)
        if next_idx == 0:
            self.sort_reverse = not self.sort_reverse
        self.sort_col = SORT_COLUMNS[next_idx]
        self._apply_filters()

    def action_show_help(self) -> None:
        self.push_screen(_HelpScreen())

    @work(exclusive=True)
    async def action_new_item(self) -> None:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, dir=str(self.feedback_dir.parent)
        )
        tmp.write(TEMPLATE.format(title="", today=date.today().isoformat()))
        tmp.close()
        tmp_path = Path(tmp.name)
        with self.app.suspend():
            open_editor(tmp_path)
        content = tmp_path.read_text()
        tmp_path.unlink()
        try:
            post = frontmatter.loads(content)
        except Exception:
            return
        title = str(post.metadata.get("title", "")).strip()
        if not title:
            return
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        item_id = next_id(self.feedback_dir)
        slug = slugify(title)
        folder = self.feedback_dir / f"{item_id:03d}-{slug}"
        folder.mkdir()
        post.metadata["title"] = title
        post.metadata["created"] = date.today().isoformat()
        frontmatter.dump(post, str(folder / "feedback.md"))
        self._reload()

    def action_quick_capture(self) -> None:
        self._input_mode = "quick"
        search = self.query_one("#search-input", Input)
        search.placeholder = "Title for quick capture..."
        search.value = ""
        search.focus()

    @work(exclusive=True)
    async def action_edit_item(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        with self.app.suspend():
            open_editor(item["md_path"])
        self._reload()

    def action_add_note(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        self._input_mode = "note"
        self._note_target = item
        search = self.query_one("#search-input", Input)
        search.placeholder = "Note text..."
        search.value = ""
        search.focus()

    def action_open_viewer(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        open_viewer(item["md_path"])

    def action_bump_volume(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        increment_volume(item["path"])
        self._reload()

    @work(exclusive=True)
    async def action_delete_item(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        confirmed = await self.app.push_screen_wait(
            _ConfirmScreen(f"Delete #{item['id']} — {item['title']}?")
        )
        if confirmed:
            delete_item(item["path"])
            self._reload()


class _ConfirmScreen(ModalScreen[bool]):
    CSS = """
    #confirm-dialog {
        align: center middle;
    }
    #confirm-box {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 60;
    }
    """
    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "deny", "No"),
        Binding("q", "deny", "No"),
    ]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            with Vertical(id="confirm-box"):
                yield Static(self.message)
                yield Static("[dim]y = yes \u00b7 n/q = no[/]")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


class _HelpScreen(ModalScreen[None]):
    CSS = """
    #help-dialog {
        align: center middle;
    }
    #help-box {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 72;
        max-height: 80%;
    }
    #help-box Static {
        margin-bottom: 1;
    }
    """
    BINDINGS = [
        Binding("question_mark", "dismiss_help", "Close", key_display="?"),
        Binding("escape", "dismiss_help", "Close"),
        Binding("q", "dismiss_help", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            with Vertical(id="help-box"):
                yield Static("[bold]Categories[/]")
                yield Static("  " + ", ".join(CATEGORIES))
                yield Static("[bold]Priorities[/]")
                yield Static("  " + ", ".join(PRIORITIES))
                yield Static("[bold]Statuses[/]")
                yield Static("  " + ", ".join(STATUSES))
                yield Static("[dim]? / q / esc = close[/]")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)


def main():
    parser = argparse.ArgumentParser(description="Feedback Tracker")
    parser.add_argument("--dir", type=str, default=None, help="Custom feedback directory")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent.parent
    feedback_dir = Path(args.dir) if args.dir else script_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)

    app = FeedbackApp(feedback_dir)
    app.run()


if __name__ == "__main__":
    main()
