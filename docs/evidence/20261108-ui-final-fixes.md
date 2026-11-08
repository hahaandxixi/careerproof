# 2026-11-08 UI final fixes

- Branch `codex/integration-20261107`, commits `9e23c44` + `2f0648d`.
- Running build: `FAuwqmRN1hY7tnhndw3vn` (3140). PR #14.
- Screenshots: `output/ui-rollout-20261108/` with `BUILD.txt`.

## Changes
- Quick palette: Esc closes from input/result/close button; Tab/Shift+Tab cycle within dialog; focus restored to opener; Chinese filtering, no-result, arrows/Enter and report-section navigation.
- Report citation positioning now scrolls to the containing requirement context, keeping title/judgment visible; duplicate same file/range locator below AI explanation removed.
- Anonymous home compressed; duplicate evidence chain removed; outer preview frame removed; registration/import controls use ink-green style.
- Piano/unsupported remains as true rule-coverage semantics in historical fixture reports; no normal source seed or demo case hardcodes it; historical reports/snapshots unchanged.

## Actual checks
- Keyboard: filter 报告 -> 6 results; Tab to result; Esc from result and close button -> closed + `.quick-command-trigger` focused; empty query shows no result and Enter does not navigate; `材料来源` and `按需补证` from report context route to `#report-materials`/`#report-supplement` with active directory.
- Frontend 716/716, TypeScript pass, build pass.
- Three report states captured separately: citation, material gap, rule-unsupported, at 1920×1080 and 1280×900.
- Register computed background checked with browser after final CSS (value recorded in screenshot run).
- No new real AI call; upload/A-B prior evidence retained.

## Unverified
- Full Tab traversal from page start across all controls not enumerated.
- 1280×800 not tested.
- Logged-in hero and fifth A/B directory remain as previously documented; no business writes.
