# Task-package baseline

Environment: Windows 11, Python 3.12.4, offline provider configuration.

Initial run before implementation:

- `python -m pytest -q`: 188 passed, 10 failed, 41 warnings, 76.86 s. The Python editable install was subsequently found to point at an older workspace, so this result is retained only as an environment diagnostic and is not used as final verification.
- `python -m ultrafast_memory.app.main doctor`: passed, 0 failed checks.
- `scripts/demo_replay.ps1`: Doctor passed; replay failed while printing `µ` through the Windows GBK console (`UnicodeEncodeError`).

After correcting the editable install to this workspace, the true pre-final suite contained 187 passes and 11 failures. Ten failures were existing Chat state/event compatibility regressions; one was the expected migration-list assertion after adding migrations. These were repaired without removing tests or weakening assertions.

The final verification report is generated separately after all implementation and regression runs.

