# Contributing / 参与改进

Useful contributions start with a concrete game-review problem: what was difficult to understand, what evidence was available, and how someone would verify an improvement.

## Run locally

Use Windows and Python 3.11+. For browser routes, install Microsoft Edge and run `py -3 -m pip install -r requirements-web.txt`. The screenshot workflow and the unit tests use the standard library.

```powershell
py -3 server.py --open
py -3 -m unittest discover -s tests -p "test_*.py" -v
```

`tests/serve_fixture.py` provides an isolated browser-test desk on port 4181 and a mock AI endpoint at `http://127.0.0.1:4182/v1`. Use a dummy key with model `colors` for the color test, or `screenshot-review` for a canned review. Never confuse these results with real model output. POST `/api/shutdown` with the desk's bootstrap token to stop the fixture and clean its temporary data.

## Keep the evidence contract

- Findings must reference provided screenshot IDs. Do not invent frames or test outcomes.
- Keep observations, inferences, and untested limitations distinct.
- Keep captured evidence when AI or game execution fails.
- Never include keys, personal game builds, saves, or `runs/` in a pull request.
- Add tests for meaningful failure boundaries and new integrations. A live paid API call must not be required for CI.
- Explain what changes for a developer using the desk; include a screenshot for a visible UI change.

## Game integrations

The current automated runner is a concrete StarTide integration in `engine.py`, not a general plugin SDK. It expects a complete Unity Windows build with the game's existing check entry points. See [adapter notes](docs/adapters.md) before extending it.

Screenshot review is independent of that runner. A new provider should implement the same validated finding contract, without introducing model-specific UI into the review itself.

## Demo assets

`web/demo/scene.html` is the original 1280×720 illustrative scene. Capture its initial HUD view as `hud.png`; add `inventory-mode` to the body to capture `inventory.png`. Keep `web/demo/report.json` clearly labeled as curated demo content.

After changing the UI or demo, run `py -3 tools/build_demo.py` and commit the updated `docs/index.html`. Open it with the network disabled: filters, evidence switching, and the image dialog should still work.

## Useful first contributions

English interface strings, keyboard interaction improvements, reproducible provider incompatibilities, and clearer verification wording are welcome. Please describe planned larger changes in an issue before replacing a subsystem. Keep each pull request focused, and state what you tested.
