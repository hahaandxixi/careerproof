# 2026-11-08 desktop UI rollout

Build: `TeFW2-0T5nQkvSlrkW3-J` on 3140, API 8140.

## Implemented

- Warm paper canvas #FAF8F5, paper #FFFEFA, ink #1D4A40 across shell and reading surfaces.
- Header at 1280 uses shortened labels (材料库/岗位/报告/投递/案例), case library link, Ctrl+K trigger.
- Anonymous homepage asymmetric hero: task entry left, continuous requirement/support/source sample right; example clearly labelled; no fake personal numbers.
- Case library rebuilt as filterable gallery with direction tabs, material composition, download/import and synthetic boundary text; no right rail.
- Quick command palette: Ctrl+K, Chinese aliases, role-filtered routes, ArrowUp/Down, Enter, Esc restores focus to trigger when no previous control; no-report context routes to /reports.
- Report page retains shared identity, directory, A/B compare and deep anchors; dark source pane beside warm reading, gap state instead of empty code window.
- Report upload continuation links retained.

## Screenshots (product pages, same final build)

`output/desktop-integration-20261106/ui-anon-final/` and `ui-rollout-final/`.
Eight required: anonymous home 1920/1280, report citation 1920/1280, report gap 1920/1280, demo 1920/1280. Extra: quick palette open/filtered, upload context, A/B.

## Verified

- 716 frontend tests passed before final focus tweak; build/typecheck passed for final build. CI result in PR #14 run.
- Real source click, report identity/directory, upload context, A/B selector observed in screenshots.
- Existing real AI evidence retained; no new AI call.

## Unverified / limitations

- Logged-in homepage remains the existing task dashboard; redesigned asymmetric hero is shown for anonymous users. Dashboard was not rebuilt into the prototype hero.
- 1280×800 was not captured; 1280×900 is the acceptance viewport.
- Quick palette actual filtering was exercised visually, but the final keyboard regression after the focus tweak awaits CI/browser rerun.
- A/B fifth directory entry was not added; existing in-report A/B section retained (prototype idea partially applied).
- No multi-project upload or failure upload page rerun in this visual batch; previous coverage stands.
- No new real AI call.
