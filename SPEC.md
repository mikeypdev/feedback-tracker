# Feedback Tracker — Design Specification

## Overview

A TUI tool for collecting, organizing, prioritizing, and tracking game feedback. One folder per item, markdown + screenshots side-by-side. One script that lists them.

---

## Architecture

```
feedback-tracker/
├── .venv/              # Python virtual environment
├── ft                  # launch script (activates venv, runs src/tui.py)
├── src/
│   └── tui.py          # the app
├── requirements.txt    # textual, python-frontmatter
└── feedback/           # source of truth, git tracked
    ├── 001-spongey-enemies/
    │   ├── feedback.md
    │   └── ttk-comparison.jpg
    └── 002-great-boss-mechanics/
        └── feedback.md
```

### Principles

- **Folders of markdown.** One TUI that lists them.
- **No database.** Parse frontmatter at startup. It's fast enough for hundreds of items.
- **No sync.** Read from disk every time. You have dozens of items, not millions.
- **Drop files yourself.** Screenshots go in the folder. No file picker needed.
- **Keyboard-driven.** All actions via hotkeys.

---

## Data Model

### Feedback folder

Each item is one folder in `feedback/`. Folder name: `{id}-{slug}`.

```
feedback/001-spongey-enemies/
├── feedback.md
├── ttk-comparison.jpg
└── act3-gameplay.mp4
```

### Markdown file (feedback.md)

```markdown
---
title: Enemies feel spongey in Act 3
category: difficulty
priority: high
status: triaged
source: Reddit u/player123
created: 2026-06-08
tags: [combat, act3, ttk]
volume: 12
---

Players report TTK feels double Act 2. Multiple complaints
about bullet-sponge behavior starting at zone 3.

![TTK comparison](ttk-comparison.jpg)

## Possible fix
Tweak the health scaling curve so Act 3 enemies aren't 2x Act 2.

---
### 2026-06-10
Fixed in build 47, need to re-test.

### 2026-06-12
Re-tested, 3 players confirmed improvement.
```

`id` is derived from the folder name prefix (e.g. `001`). `updated` is the file's mtime.

`volume` is optional (defaults to 1). How many people reported this. Used for sorting/filtering.

Notes are dated `### YYYY-MM-DD` headings appended to the body. Added via the `+` hotkey.

### Enums

| Field      | Values                                         |
|------------|------------------------------------------------|
| category   | `difficulty`, `gameplay`, `fun`, `understanding`, `narrative`, `visual`, `audio`, `ux`, `other` |
| priority   | `critical`, `high`, `medium`, `low`            |
| status     | `new`, `triaged`, `planned`, `in-progress`, `addressed`, `wontfix`, `duplicate` |

---

## Screens

### List + Detail (one screen, split pane)

```
┌─ Feedback Tracker ──────────────────────────────────────────── [n]ew [q]uit ┐
│                                                                               │
│ [/] search: ___  [c]ategory: ___  [p]riority: ___  [s]tatus: ___            │
│                                                                               │
│   #  │ Vol │ Pri   │ Status   │ Category   │ Title                        │        │
│ ─────┼─────┼───────┼──────────┼────────────┼──────────────────────────────│        │
│   1  │ 12  │ HIGH  │ triaged  │ difficulty │ Enemies feel spongey in Ac.. │─────── │
│   2  │  3  │ MED   │ new      │ fun        │ Great boss fight mechanics   │ #1:    │
│   3  │  1  │ LOW   │ new      │ gameplay   │ Crafting menu unclear ⚠      │        │
│      │     │       │          │            │                              │ diff.. │
│      │     │       │          │            │                              │ high   │
│      │     │       │          │            │                              │ triag  │
│      │     │       │          │            │                              │ vol 12 │
│      │     │       │          │            │                              │        │
│      │     │       │          │            │                              │ Play.. │
│      │     │       │          │            │                              │ repor..│
│      │     │       │          │            │                              │        │
│      │     │       │          │            │                              │        │
│                                                                               │
│ 47 items · 12 new · 5 high · 2 critical   [n]ew [N]quick [e]dit [+]note [q]uit │
└───────────────────────────────────────────────────────────────────────────────┘
```

`⚠` marks items that have been `new` for over 7 days (stale).

### Editor (modal overlay)

Opens `$EDITOR` (vim, nano, etc.) directly on `feedback.md`. When the editor closes, the list refreshes.

For new items: opens editor on a temp file pre-filled with a frontmatter template. On save, creates the folder and moves the file in.

---

## Actions

| Key      | Action                                     |
|----------|--------------------------------------------|
| `j`/`k`  | Move selection up/down                     |
| `N`      | Quick capture — title only, saves as `new` (for fast jotting during playtests) |
| `n`      | Create new item (opens full editor)        |
| `e`      | Edit selected item (opens editor)          |
| `+`      | Append dated note to selected item         |
| `d`      | Delete selected item (confirm, then `rm -r`) |
| `v`      | Increment volume on selected item          |
| `/`      | Focus search (grep-style across all feedback.md files) |
| `c`      | Cycle category filter                      |
| `p`      | Cycle priority filter                      |
| `s`      | Cycle status filter                        |
| `x`      | Clear all filters                          |
| `tab`    | Cycle sort column                          |
| `o`      | Open in system markdown viewer              |
| `q`      | Quit                                       |

---

## Implementation (single file)

`src/tui.py` is one Python module, launched via `ft`. Roughly:

```python
# read all folders, parse frontmatter, return list of dicts
# computes staleness: marks items that have been "new" for > 7 days
def load_feedback(feedback_dir: Path) -> list[dict]

# get next available id
def next_id(feedback_dir: Path) -> int

# title → url-safe slug, max 50 chars
def slugify(title: str) -> str

# create folder + feedback.md from template
def create_item(feedback_dir: Path, title: str) -> Path

# quick capture: title only, no editor, minimal frontmatter
def quick_capture(feedback_dir: Path, title: str) -> Path

# append a dated note to the body (### YYYY-MM-DD\n<text>)
def append_note(item_path: Path, text: str) -> None

# increment the volume field in frontmatter
def increment_volume(item_path: Path) -> None

# compute summary counts for the stats footer
def compute_stats(items: list[dict]) -> dict

# delete folder (takes the item's path directly)
def delete_item(item_path: Path) -> None

# open $EDITOR on file, wait for it to close
def open_editor(path: Path) -> None

# open in system viewer (open on macOS, xdg-open on Linux)
def open_viewer(path: Path) -> None

# filter in-memory list by category, priority, status, and/or text query
def filter_items(items: list[dict], category, priority, status, query) -> list[dict]

# sort in-memory list by column key
def sort_items(items: list[dict], column: str, reverse=False) -> list[dict]

# extract unique enum values present in data (for filter cycling)
def derive_enums(items: list[dict]) -> tuple[list[str], list[str], list[str]]
```

The Textual app:
1. `load_feedback()` on startup
2. Display in a DataTable widget
3. Filters narrow the in-memory list (cycle with hotkeys)
4. Tab cycles sort column; wraps back to first column toggles reverse
5. `n`/`e`/`d` call the functions above
6. After editor closes, `load_feedback()` again (it's fast)

---

## Setup

```bash
cd feedback-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `ft` launcher script handles activation:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python src/tui.py "$@"
```

## CLI

```
./ft              # launch TUI
./ft --dir PATH   # use custom feedback directory
```

No subcommands. If you need to script, `grep` and `ls` the `feedback/` directory.

---

## Tech Stack

| Component   | Choice              |
|-------------|---------------------|
| Language    | Python 3.11+        |
| TUI         | Textual             |
| Frontmatter | python-frontmatter  |
| Editor      | `$EDITOR` / subprocess |

Four dependencies. One file. Venv keeps them isolated.

---

## Disk layout

```
feedback-tracker/
├── .venv/
├── ft
├── src/
│   └── tui.py
├── requirements.txt
└── feedback/
    ├── 001-spongey-enemies/
    │   ├── feedback.md
    │   └── ttk-comparison.jpg
    ├── 002-great-boss-mechanics/
    │   └── feedback.md
    └── 003-crafting-menu-unclear/
        ├── feedback.md
        └── menu-confusion.jpg
```

`.venv/` is gitignored. `requirements.txt` is tracked.

---

## Maybe later

- SQLite if parsing frontmatter ever gets slow
- Inline markdown rendering in the detail pane
- Bulk status changes
- `ft list` / `ft stats` CLI subcommands for scripting
- Configurable categories via config file
- Duplicate linking (#14 is a dup of #1)
- Session tags for grouping playtest events
