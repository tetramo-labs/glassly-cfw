# Fixed read-only topology diagnostics

This is a proposed interface, not implemented or run here. It supplements static[report.md](report.md) using the existing normal task and response ownership conventions. It must expose **no arbitrary address, length, GPIO, SPI command or function pointer input**.

## Preferred: passive initialized-state snapshot

Read only these fixed native RAM scalar slots from the pinned image. Normalize pointers to known enums/booleans; never dereference them or disclose them as an arbitrary memory view. A short existing native critical-enter/exit pair may bracket only the scalar copy, with no allocation, response creation, SPI operation or wait inside. Alternatively explicitly mark a changed double-sampled snapshot inconsistent. Never dereference the CUS8 singleton to read capacity: another task can free it.

| Output | Fixed source | Interpretation |
|---|---|---|
|`xip0Initialized`,`xip1Initialized`|u8`0201234c/0201234d`|Initialization wrapper has run; flag alone does not guarantee success|
|`xip0Driver`,`xip1Driver`|u32`02012330/02012334`|Normalize`02010898`→manufacturer85 family,`020107f0`→c8 family,0→none, all other values→unknown|
|`xip0QuadConfigured`,`xip1QuadConfigured`|u8`02012338/02012339`|Driver's configuration path reached flag assignment; not a new hardware measurement|
|`xip1ProbeValid`,`xip1ProbeCode`|u8`0205c8e0`, u32`0205c8e4`|Use code only with valid and85-family driver; contains legacy ID, extra byte, first UID-derived byte, not full unique ID|
|`sharedC8ProbeValid`,`sharedC8ProbeCode`|u8`02012350`, u32`02012354`|Explicitly shared cache; do not label it device1 capacity|
|`generalSpiBackendKnown`|u32`020124d0 == 02010c6c`|Known PY25/BY25 function table selected|
|`generalSpiReady`|u8`020124d4`|Set only after successful general-SPI initializer including68:18/68:19 identity check|
|`generalSpiMutexPresent`,`generalSpiSemaphorePresent`|u32`020124d8/020124dc != 0`|Prerequisite booleans, not proof of ownership/free status|
|`generalSpi0Configured`|low byte`0205c2ac` bits0..1|Native initialized/configured state|
|`generalSpiPinsMatch`|u32`0205c26c/270/274/278`, u8`0205c27c`|Compare to`5,102,3,4,0`; report boolean rather than a general register dump|
|`cus8ContextPresent`|u32`02011e48 != 0`|Transient query/install context may be live; does not imply persisted directory|
|`cus8ValidatedPackageState`|u8`02011e50`|Native package-validation/active-state flag; context NULL alone is insufficient|

The85 cache code is a timing/device probe composite; its high16bits contain the legacy manufacturer/device ID. The full16-byte UID is neither required nor returned. If exposure is unnecessary, return only that high16bit value plus a recognized timing-code enum instead of the full composite.

A recognized initialized XIPdevice1 driver plus ready known generalSPI backend corroborates the distinct supported identity predicates. If generalSPI is not ready, report **not initialized/unknown**, not absent or same-chip. Do not call its initializer to fill missing data: `04346966` reconfigures GPIO/SPI and sendsAB/06/B7/status operations, so it is not a read-only identity query.

## Optional initialized-only ID confirmation

No new bus call is needed for the first snapshot. If later exact live ID bytes are still useful, these two existing functions are narrower than constructing arbitrary SPI requests:

```c
uint16_t xip_legacy_id(unsigned device);          //02005bec; force device1
int general_spi_id(void *owned_out20);             //0434633e
```

XIP ID must be called from an initialized normal task under the existing per-device lock`04329912(1)` / `0432994a(1)`, with no nested custom flash lock or long critical section. It sends only command90 and receives2bytes. Require the initialization/known-driver prerequisites first; reject0/ffff and inconsistent repeats. Its wrapper does not propagate a lower read status, so retain this limitation in the result. Hardware wait is not cancellable through a host timeout. Capacity getter`04329d62(1)` merely repeats this bus read and derives a value; it is unnecessary if the2bytes are already obtained.

General-SPI ID uses its own native mutex and semaphore, status readiness check, synchronous command90 transfer, and a20-byte output layout: u32code6818/6819 followed by a bounded16-byte name. Require known backend, readyflag, mutex/semaphore-present and configured pin snapshot before entry. It returns0 only after validating the repeated manufacturer/device bytes; failures return native nonzero codes. Use owned zeroed20-byte memory and emit fields only on success. Do not hold the XIP mutex while calling it. It does not issue program/erase or four-byte-enable commands; those occur in the separate initializer. The helper logs/errors and native waits remain part of its behavior.

The UID helper`02005c8e(device,out16)` and raw SPI transaction APIs are deliberately excluded. The UID helper returns0 without propagating lower status and contributes nothing necessary to this topology decision. There is no reason to expose arbitrary RAM, MMIO, unique-ID or raw transaction access.

## Reset/CUS8 observation

A passive query just after a genuine new-image boot can confirm the expected CUS8 boolean state, but do not interpret non-NULL as an old-capacity leak: normal tasks may already have created a **new** context. Startup clearing proves old pointers are discarded; whether a new context is present depends on current workload. If actual current capacity is needed later, obtain it through the properly owned native store query or a proven synchronized owner, not an unsynchronized context-pointer dereference. An all-ff directory can coexist with the transient successful query context and is not a substitute for these lifecycle semantics.
