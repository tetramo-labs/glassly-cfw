#!/usr/bin/env python3
"""Full-store reader/diagnostics contracts with the canary image's exact identity."""
import check_full_store_read_contract as suite
from memomind_flash_read import CANARY_PROFILE
suite.FULL_STORE_PROFILE=CANARY_PROFILE
if __name__=='__main__':suite.main()
