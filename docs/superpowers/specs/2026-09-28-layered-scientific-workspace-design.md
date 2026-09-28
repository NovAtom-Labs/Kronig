# Layered Scientific Workspace Design

## Goal

Refine the Agent Kronig desktop shell so the file and results canvas is unmistakably primary, with repository and agent tools presented as quiet, retractable sidebars.

## Approved direction

- Preserve the repository, workspace, and agent pane structure and all resize behavior.
- Keep the central workspace visually uninterrupted, borderless, and dominant.
- Present the repository and agent panes as restrained rounded sidebars with 6 px spacing.
- Allow both sidebars to retract on desktop and return from compact header controls.
- Remove permanent full-height dividers and unnecessary full-width horizontal rules.
- Reveal resize affordances only on hover, focus, or active drag.
- Group controls through spacing and quiet inset surfaces instead of repeated borders.
- Keep scientific tables, plots, source code, and result data dense and precise.
- Preserve the dark, professional visual language without glass effects, gradients, oversized cards, or decorative animation.
- Preserve usable drawer behavior at tablet and narrow widths.

## Non-goals

- No workflow, simulator, agent runtime, result schema, or persistence changes.
- No information architecture changes.
- No new UI framework or runtime dependency.

## Acceptance criteria

- The central canvas has no enclosing card treatment or divider borders.
- Both desktop sidebars can be independently collapsed, restored, and resized.
- Header, file viewer, repository controls, agent tabs, activity, and composer share one restrained surface language.
- Resizing does not produce inconsistent gaps.
- Tablet and narrow drawers remain reachable and visually contained.
- Existing UI, JavaScript, backend, and desktop tests remain green.
