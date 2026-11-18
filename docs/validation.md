# Validation for 0.2.0

On 2026-11-18 the Windows x64 ZIP was extracted to a fresh directory. The included launcher started a second installation beside an existing local desk. Its embedded Python imported the bundled Playwright and ran Microsoft Edge.

| Real UI run | Observed result |
| --- | --- |
| Moss Harbor, 1280 × 720 | The task text, Tab, inventory title, Escape and restored pickup message passed. Five screenshots were exported. |
| Moss Harbor, 800 × 600 | A full-scene visibility check failed at the first step. The report preserved the 1280 × 720 scene bounds, window dimensions and screenshot. |
| Rustfire opening, 1280 × 720 | The entry button, click, movement input, pause input and pause title passed. Five screenshots were exported. Movement distance and game balance were outside the assertions. |

The app reloaded a prior route, opened a failure image, displayed local history and downloaded the evidence bundles. All 23 offline tests passed. The bundled exercise and illustrative report use original assets. External provider testing for this release used local mocks.

## Previous validation for 0.1.0

Date: 2026-11-15. Local checks were run on Windows with Python 3.12 and a Chromium-based browser. GitHub Actions is configured for Python 3.11 and 3.12; remote CI has not run before publication.

## Automated checks

20 tests passed with:

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
```

Coverage includes:

- Consistent game-check reports, valid evidence references, finite in-bounds annotation rectangles.
- Interrupted jobs, cancellation, evidence preservation, and invalidation when game files change.
- Persistent finding state, guarded local requests, evidence path traversal rejection, and save-file exclusion.
- Encrypted profile persistence, metadata without keys, draft validation, and rollback when configuration writes fail.
- Actual HTTP exchanges with a **local mock provider** for both supported protocols, PNG payloads, and auth headers.
- Redacted errors, rejected redirects, malformed/truncated model output, prompt cancellation, and no automatic retry.
- Imported-image reviews without a game or Codex; invalid imports rejected before history/network activity; failed reviews retaining images.

Frontend JavaScript also passed `node --check web/app.js`.

## Browser workflow

In an isolated fixture with temporary history and dummy credentials:

- Added a custom profile, tested color recognition, saved it, and verified the password field cleared.
- Imported two PNGs, received a mock review, changed a finding to ready-to-retest, and verified it persisted after reload.
- Downloaded the evidence ZIP through the UI. It contained Markdown, JSON, and both screenshots; no dummy API secret was present.
- Checked Claude and Qwen presets and the settings dialog at widths 320, 390, 768, 1024, and 1440 px without horizontal overflow.
- Exercised the demo's finding selection, filters, gallery, and image dialog at the same widths. No page script errors occurred. Demo mode made no API requests.

The offline demo is generated from the same UI, with its report and PNG images embedded. Its demo branch was browser-tested over local HTTP; automated browser access to `file:` URLs was unavailable. The generated artifact was checked for self-contained resources and JavaScript syntax.

## Real integrations and limits

The existing StarTide + Codex route was previously exercised locally: four game-check groups, 217 checks, 34 captured images, and 10 selected images reviewed. That historical result belongs to its specific private game candidate; it is not a test of an arbitrary game and those private assets are not distributed here.

Grok, Gemini, Claude, Qwen, and OpenAI transports were implemented using official documentation and validated with mocks. **No claim is made that every provider/model/account was live-tested.** The in-app image test lets a user check their actual configuration before a review.

No validation is claimed for macOS/Linux credential storage, arbitrary-game autoplay, audio, real-time animation, performance conclusions from images, or AI agreement with a human reviewer.
