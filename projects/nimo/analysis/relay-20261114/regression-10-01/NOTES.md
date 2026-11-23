# GLASSLYCFW/10 offline regression

`tests/run_tests.py --revision 10`: stages 01, 02, 03, 05 and 06 passed. Stage 04
(portable scene core vs the pinned G2 reference) stopped at the hash pin because the
MemoMind checkout it reads the reference from had uncommitted edits under
`tests/g2_compat/upstream` at the time. Nothing under `runtime/portable/` changed in
this revision; the stage was rerun in `04_portable_host_rerun/` against the committed
reference (MemoMind HEAD, `git archive`, commit e889569f as pinned) with both suites
passing.
