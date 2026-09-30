# ripple

Test impact analysis for Python repos: given a git diff, run only the tests that could be affected.

**Status:** early development.

**Core invariant:** when in doubt, run more tests. Skipping a test that should have run is a bug.