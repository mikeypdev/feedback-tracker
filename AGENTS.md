# Feedback Tracker

TUI tool for collecting, organizing, and tracking game feedback. Single-file Python app built on Textual.

## Commands

```bash
# Run the app (handles venv activation)
./ft
./ft --dir /path/to/custom/feedback   # use a different feedback directory

# Run tests (requires venv activated or deps installed)
pytest

# Setup from scratch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tests use `pytest-asyncio` with `asyncio_mode = auto` (configured in `pytest.ini`). No extra flags needed — `pytest` discovers and runs both sync and async tests.

## Architecture

Everything lives in `src/tui.py` (~630 lines). There is no separate data layer module.

**Data model**: Each feedback item is a folder `feedback/{NNN}-{slug}/` containing `feedback.md` with YAML frontmatter (title, category, priority, status, source, created, tags, volume) plus a markdown body. The ID is parsed from the folder name prefix, not stored in the frontmatter.

**No database**: `load_feedback()` parses all frontmatter files from disk on startup and after every mutation. This is intentional — fine for hundreds of items.

**App structure** (`FeedbackApp`):
- Split-pane layout: `DataTable` (left, 2fr) + `DetailPane` (right, 1fr)
- In-memory `self.items` list (all items) and `self.filtered` (after filters/sort)
- `_reload()` re-reads disk → `_apply_filters()` → `_populate_table()` + `_update_stats()` + `_show_detail()`
- Editor actions (`n`, `e`) use `self.app.suspend()` + `subprocess.run($EDITOR)` — blocking the TUI while editing
- The search input doubles as the input for quick capture and notes, switching via `self._input_mode`

**Helper classes**: `DetailPane(Static)` renders the selected item's details. `_ConfirmScreen(ModalScreen[bool])` is the delete confirmation dialog.

## Key Functions (top-level in tui.py)

- `load_feedback(feedback_dir)` → `list[dict]` — parses all folders, returns sorted by ID
- `next_id(feedback_dir)` → `int` — max existing ID + 1
- `slugify(title)` → `str` — lowercases, strips specials, hyphens for spaces, max 50 chars
- `create_item(feedback_dir, title)` → `Path` — creates folder + feedback.md from template
- `quick_capture(feedback_dir, title)` → `Path` — like create_item but re-dumps with correct title
- `append_note(item_path, text)` — appends `### YYYY-MM-DD\n{text}` to the markdown body
- `increment_volume(item_path)` — bumps the volume frontmatter field by 1
- `delete_item(item_path)` — `shutil.rmtree`
- `open_viewer(item_path)` — `Popen` with `open` (macOS) or `xdg-open` (Linux), non-blocking
- `open_editor(path)` uses `subprocess.run` (synchronous)
- `filter_items(items, category, priority, status, query)` — title + body search
- `sort_items(items, column, reverse)` — sort by id/volume/priority/status/category/title
- `derive_enums(items)` — extracts unique categories/priorities/statuses from data for filter cycling

## Enum Constants

- **Categories**: `difficulty`, `gameplay`, `fun`, `understanding`, `narrative`, `visual`, `audio`, `ux`, `other`
- **Priorities**: `critical`, `high`, `medium`, `low`
- **Statuses**: `new`, `triaged`, `planned`, `in-progress`, `addressed`, `wontfix`, `duplicate`

Filter cycling uses `derive_enums()` which returns only values present in current data, falling back to the full lists above when data is empty.

## Staleness

Items with `status: "new"` and `created` date > 7 days ago are marked `stale: True`. Displayed with a `⚠` marker in the table and detail pane.

## Testing

Two test files, both importing directly from `src.tui`:

- `tests/test_data_layer.py` — pure-function tests for load, create, filter, sort, slugify, frontmatter round-trips. Uses `tmp_path` fixture with a helper `_write_item()` that creates folder + frontmatter.
- `tests/test_tui.py` — async Textual app tests using `pytest_asyncio` and `app.run_test()`. Tests mounting, navigation (DataTable cursor), filter cycling, sort, quick capture, notes, delete confirmation, search, and stale markers. Uses `@pytest.mark.asyncio` on each test method. The `app` fixture provides `(app, pilot)` via `async with a.run_test(size=(120, 30))`.

**Note**: Both test files define their own `_write_item()` helper — they are not shared.

## Gotchas

- `create_item` uses a `TEMPLATE` string with `"{title}"` placeholder but writes the template literally for the "new item" flow — the actual title is filled in from parsed frontmatter after editing the temp file. `quick_capture` calls `create_item` then immediately re-dumps the post with the correct title.
- The `action_new_item` writes to a temp file in the project root (not `feedback/`), opens the editor on it, then parses the result and creates the real folder. If the user blanks the title, the temp file is silently discarded.
- `open_editor` uses `subprocess.run` (synchronous) inside `@work(exclusive=True)` async methods with `self.app.suspend()` — this is the Textual pattern for shelling out to blocking processes.
- The `_input_mode` state machine (`"search"` | `"quick"` | `"note"`) multiplexes the single `Input` widget. Changing behavior requires updating both `on_input_changed` and `on_input_submitted`.
- CSS is embedded as a string in `FeedbackApp.CSS` rather than in a separate `.tcss` file.
- LSP import errors for `textual` and `frontmatter` are expected — these deps live in the venv, not globally.
