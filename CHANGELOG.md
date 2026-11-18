# Changelog

## 0.2.0 — 2026-11-18

- Replay configurable keyboard, click, text and viewport checks in a local browser game. Keep screenshots, failure evidence and the original route for retesting.
- Try the bundled Moss Harbor inventory exercise without credentials, or load the Rustfire opening preset for an independently running game.
- Import an existing structured review and match evidence to the original filenames.
- Launch from a portable Windows x64 package alongside other installations.

## 0.1.0 — 2026-11-15

First public-source candidate. Repository publication is a separate step.

- Import up to 10 screenshots from any game and receive evidence-linked visual findings.
- Select Codex login or configure Grok, Gemini, Claude, Qwen, OpenAI API, and compatible providers.
- Encrypt provider keys with Windows DPAPI; test image understanding before reviewing.
- Preserve evidence when a review fails or is stopped; retain actual provider/model metadata per run.
- Review annotated screenshots, prioritize changes, track their state, and export Markdown plus evidence ZIPs.
- Include an offline interactive demo built from original illustrative scenes.
- Retain the instrumented StarTide automated playtest integration, separately from generic screenshot review.
- Add Windows CI, provider/adapter documentation, and contribution templates.

Known limits: Windows-first; Chinese UI/output; screenshot review cannot validate dynamic play; automated play is game-specific; provider transports were tested with local mocks, not paid accounts for every listed provider.
