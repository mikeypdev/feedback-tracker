# Feedback Tracker

Keyboard-driven TUI for collecting, organizing, and tracking game feedback. Each item is a folder with a markdown file — no database, no sync.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
./ft              # launch with default feedback/ directory
./ft --dir PATH   # point at a different feedback directory
```

## Keybindings

| Key | Action |
|-----|--------|
| `j`/`k` | Move selection up/down |
| `n` | Create new item (opens editor) |
| `N` | Quick capture — title only, saves as `new` |
| `e` | Edit selected item (opens editor) |
| `+` | Append dated note to selected item |
| `d` | Delete selected item (confirmation prompt) |
| `v` | Increment volume on selected item |
| `/` | Focus search (filters across titles + bodies) |
| `c` | Cycle category filter |
| `p` | Cycle priority filter |
| `s` | Cycle status filter |
| `o` | Open in system markdown viewer |
| `x` | Clear all filters |
| `tab` | Cycle sort column |
| `q` | Quit |

## Feedback Items

Each item is a folder in `feedback/`:

```
feedback/001-spongey-enemies/
├── feedback.md
├── ttk-comparison.jpg
└── act3-gameplay.mp4
```

The markdown file uses YAML frontmatter:

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

Players report TTK feels double Act 2.

![TTK comparison](ttk-comparison.jpg)

### 2026-06-10
Fixed in build 47, need to re-test.
```

**Fields:**

| Field | Values |
|-------|--------|
| category | `difficulty`, `gameplay`, `fun`, `understanding`, `narrative`, `visual`, `audio`, `ux`, `other` |
| priority | `critical`, `high`, `medium`, `low` |
| status | `new`, `triaged`, `planned`, `in-progress`, `addressed`, `wontfix`, `duplicate` |
| volume | Integer, defaults to 1. How many people reported this. |

Items stay `new` for over 7 days are marked stale (⚠).

## Separating Tool and Data

The `--dir` flag lets you keep feedback data in its own repo:

```bash
./ft --dir ../game-feedback
```

## Tech Stack

- **Python 3.11+**, [Textual](https://textual.textualize.io/) for TUI, [python-frontmatter](https://github.com/eyeseast/python-frontmatter) for parsing
- Four dependencies, one source file
