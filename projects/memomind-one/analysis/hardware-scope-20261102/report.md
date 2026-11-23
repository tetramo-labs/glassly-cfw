# Hardware scope audit

The final updated scope is consistent with the user exclusions. All96 pinned upstream source/license files match UPSTREAM.json. Inventory regeneration check and all8 scope regressions pass. No production/test source or device state was changed by this audit.

Historical coverage remains46 C scenarios,746 assertion sites and21 Bun cases. Required coverage is39 C scenarios,654 assertion sites and11 Bun cases: six keyboard scenarios/86 sites and one ring-battery scenario/six sites are excluded from native parity obligations. Sources and original scenario bodies remain preserved. The unchanged mixed upstream/reference binary still executes battery and keyboard structural checks; this is explicitly reported as historical/reference coverage, not a renewed requirement for nonexistent accessories.

The mixed upstream_host_test.c entry remains required and platform-specific/incomplete, with four required scenarios (routing, settings, headings, BLE link) and72 required assertion sites of its original78. Headings is still required. Mixed settings notes explain that native responses must distinguish unsupported selectors. No mixed suite was relabeled complete by the scope change.

Compass mode10 remains a required missing native sampling/ownership adapter in COMMAND_PARITY. Raw IMU is separately and explicitly required, including native samples/stream, metadata, start/stop, ownership and cleanup; gesture exclusion does not remove sensor access. Single-button input and its actual observation/forwarding remain required, as does ALS. Generic wake ownership, microphone, notification, settings, transport, drawing and full capacities remain required. Head-up/swipe/ring-touch acceptance is excluded rather than counted complete.

Exactly19 required suite/integration rows remain incomplete. Both analysis/parity-status.json and analysis/storage-integration-plan.json contain the same required coverage counts, pending-file list and required hardware features as inventory.json. full_memo_suite_port_complete remains false and unimplemented/platform-specific entries are not passes. Historical aggregate count fields retain the old scope as historical run evidence; current required_reference_coverage is39/654/11.

One stale field was found during review: the mixed upstream row's pending_platform_boundaries still required a native accessory battery adapter. Root corrected this to "native timestamped compass/raw IMU sensor adapters" and regenerated inventory. The final source hashes and checks in report.json cover that corrected version.

Commands run:

```sh
python3 tests/g2_compat/inventory.py --check
python3 -m unittest discover -s tests/g2_compat -p test_scope.py -v
```

Final outputs are inventory-check-final.stdout/stderr and scope-tests-final.stdout/stderr. Upstream hashes are saved in upstream-hashes.json. These are scope/source-integrity tests and mocked orchestration regressions, not hardware sensor/button verification. No original hardware harness was executed.
