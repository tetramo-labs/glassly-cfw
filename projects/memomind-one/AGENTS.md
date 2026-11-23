# Project workflow

- After every firmware flash, record the exact image/runtime hashes, transfer
  outcome, boot verification and hardware checks. Distinguish a reboot ACK from
  successful boot; document incomplete checks explicitly.
- Commit the relevant source, tests and verification/status records, then push
  to origin after each flash. Do not leave a successful flash only in the local
  working tree. Do not repeat an OTA merely to obtain a commit.
- Origin is https://github.com/tetramo-labs/glassly-memomind-one-cfw and the
  repository must remain private.
- Original project code is MIT. Preserve existing MIT licenses/notices on
  upstream and derived code.
- CFW version strings use `GLASSLYCFW/N`, where N is a numeric revision.
  Increment N for every firmware flash; record the matching revision, image and
  runtime hashes in the catalog, transfer evidence and boot verification.
- Keep raw captures, firmware/APKs, toolchains, secrets and generated binaries
  local. Analysis is ignored by default; explicitly add relevant source helpers,
  recipes, notes and verification summaries.
- Preserve sealed historical captures and evidence. Use a new directory for
  each device attempt and record any later confirmation separately.
- Keyboard/HOGP, ring battery, gestures, mode5 sound/tone commands and volume gating are out of scope. Single-button input,
  compass/raw IMU/ALS, notifications, microphone capture/streaming and applicable G2 parity remain in scope.
