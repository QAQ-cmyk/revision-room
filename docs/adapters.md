# Automated playtest integration

For browser games, use [configurable Playwright routes](web-routes.md). The native game runner includes one adapter for instrumented Windows builds of StarTide / 星潮漂流. The public package does not include that game's executable, source, or assets. Everyone can use screenshot review without it.

The existing runner expects this sibling layout:

```text
workspace/
  RevisionRoom/
  Build_YourVersion/
    StarTide.exe
    UnityPlayer.dll
    StarTide_Data/Managed/Assembly-CSharp.dll
```

`validate_game()` accepts only complete builds under the app's parent directory, with the existing `OpeningExperienceChecks` and `ChapterRuntimeChecks` markers. This is a supported-build check, not verification that an executable is trustworthy.

The current process contract in `ReviewEngine._run_test()` uses:

| Check | Argument | Expected report |
| --- | --- | --- |
| Opening experience | `--chapter-experience` | `opening_report.json` |
| Game systems | `--chapter-test` | `runtime_report.json` |
| Save reload (once per save) | `--chapter-reload` | `reload_report.json` |

Each launch receives a separate `--save-root` and `--report-root`, window settings, and Unity's `-logFile` argument. Reports contain a Boolean `passed`, lists of successful `checks` and `errors`, and optional scope/timing fields. Screenshots are collected from the opening and systems report directories. Saves are excluded from evidence exports.

To integrate another game, implement its actual launch, input, save isolation, and capture workflow; then generalize the runner with tests and fixtures. Merely renaming another executable or adding marker strings is not integration. Document what actions are scripted, what uses fixture state, and what remains untested.

Keep generic screenshot review usable without any game-specific files. Prefer a small explicit integration over a claim that an arbitrary game can be understood automatically.
