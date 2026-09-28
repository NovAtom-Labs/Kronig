# Layered Scientific Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the central research canvas dominant and turn the repository and agent areas into restrained, retractable sidebars.

**Architecture:** Keep the existing workspace contract and extend the layout controller with deterministic desktop collapse behavior. Use CSS for a borderless central canvas, secondary sidebars, compact hierarchy, and responsive drawer overrides.

**Tech Stack:** Server-rendered HTML, CSS, vanilla JavaScript, pytest static UI contracts.

**Spec:** `docs/superpowers/specs/2026-09-28-layered-scientific-workspace-design.md`

## Global Constraints

- Preserve all existing workflow and pane-resizing behavior.
- Make both sidebars independently retractable on desktop.
- Do not add a UI framework or external assets.
- Keep scientific data dense and legible.
- Avoid glass effects, gradients, oversized cards, and decorative animation.
- Add behavior with a failing test first and run the complete suite before committing.

## Review Focus

- Desktop resizing must retain an even visual gutter between panes.
- Tablet repository and narrow agent drawers must not inherit invalid grid margins.
- Rounded panes must clip file, result, and chat content correctly.
- Compact agent controls must remain readable at the minimum pane width.
- Source, table, and results views must retain their data density.

---

### Task 1: Encode the dominant-canvas shell contract

**Files:**
- Modify: `tests/unit/web/test_ide_javascript.py`
- Modify: `src/tcad_agent/web/static/theme.css`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `src/tcad_agent/web/templates/ide.html`

**Interfaces:**
- Consumes: existing `.ide-shell`, `.workspace-browser`, `.workspace-main`, `.agent-panel`, and `.pane-resizer` selectors.
- Produces: a borderless primary canvas and visually secondary sidebars.

- [x] **Step 1: Write the failing CSS contract test**
- [x] **Step 2: Run the focused test and confirm it fails**
- [x] **Step 3: Implement the central canvas, secondary sidebars, and hover-only resize indicators**
- [x] **Step 4: Run the focused UI tests and confirm they pass**

### Task 2: Add retractable sidebars and refine internal hierarchy

**Files:**
- Modify: `tests/unit/web/test_ide_javascript.py`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `src/tcad_agent/web/static/ide-layout.js`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/templates/ide.html`

**Interfaces:**
- Consumes: Task 1 surface tokens and pane shells.
- Produces: collapsible desktop sidebars plus minimal repository, file viewer, agent, activity, composer, and results grouping at all supported widths.

- [x] **Step 1: Add failing assertions for internal grouping and responsive drawer containment**
- [x] **Step 2: Run the focused test and confirm it fails**
- [x] **Step 3: Implement desktop collapse behavior, compact internal hierarchy, and responsive overrides**
- [x] **Step 4: Run UI, desktop, and complete project verification**
