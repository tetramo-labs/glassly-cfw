#!/usr/bin/env python3
"""Run retained diagnostics-profile suites on the RESET-trim candidate."""
import sys
from reset_undo_trim_runtime_emulator_test import PINNED_SHA
import diagnostic_command_existing_runtime_emulator_test as retained
import diagnostic_command_runtime_emulator_test as diagnostic
if __name__=='__main__':
    # Only select a different machine-code digest; retained assertions and
    # already-documented diagnostics adapters execute unchanged.
    retained.PINNED_SHA=PINNED_SHA;diagnostic.PINNED_SHA=PINNED_SHA
    if '--suite' in sys.argv and sys.argv[sys.argv.index('--suite')+1]=='diagnostics':
        i=sys.argv.index('--suite');del sys.argv[i:i+2];diagnostic.main()
    else:retained.main()
