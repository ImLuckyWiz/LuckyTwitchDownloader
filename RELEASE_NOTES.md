## v1.4.2

No visible changes in this version. The app looks and behaves exactly as in v1.4.1. This release reorganizes the code and adds automated tests, to make future updates safer.

### Under the hood
- The Plan tab code now lives in its own module (`ui/plan_tab.py`), with shared colours and fonts in `ui/common.py`.
- Added an automated test suite (203 tests) covering the download engine and the Plan tab.

### Known issue
- **Split at selected clip**, used twice on the same clip, writes an empty range (for example `0:59:57 - 0:59:57`) into the cut text, which the planner then rejects. Not fixed yet.
