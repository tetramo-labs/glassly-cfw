# Optional GM response-filter read-only review

No blocking defect found. The six root tests cover coalesced main/settled messages, delayed notifications, fragmentACKs and early rejection, duplicate accepted replies, filter errors, and a256-notification burst. An independent analysis-local Swift executable exercised11 additional/default edge cases against the actual production core; all passed. `checks.json` lists every case and `report.json` pins source, executable and root test-log hashes.

Matching nonempty business messages pass through the optional throwing filter. False routes the message to unsolicited; true selects it, with a second accepted reply in the same decoded read rejected. EmptyACKs bypass the filter; intermediate fragment heads are still checked. An accepted early business response stops subsequent writes. A filter throw after an otherwise acceptable reply rejects the whole decoded read. Without a filter, existing last-match final-response and first-business intermediate behavior remains unchanged.

The intended boundaries remain significant: the filter only sees the current event/service/command, not other events. A delayed duplicate/notification is only seen on the next read. Other-event messages route to the nonthrowing unsolicited callback, so a strict live client must record any schema/correlation failure and check it before its next command. Returnfalse only for a positively validated notification; native rejection must be accepted as a business reply or throw. No notification drain, session poison flag or automatic recovery was introduced.

No production/test source, device or firmware files were changed. The analysis executable uses synthetic transport only and makes no hardware claims.
