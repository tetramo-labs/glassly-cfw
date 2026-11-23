# Glassly Halliday G2 CFW

Local research on Halliday G2 setup and firmware updates. The Android companion package is `com.halliday.oasis`. The first session used Halliday 1.2.0 (build 200) on a rooted Pixel 9 Pro.

## Capture

Use a phone with a working Bluetooth HCI snoop log. The collector reads it through root ADB and records companion app logcat by Android UID. The HCI log includes other Bluetooth traffic during the capture window. Keep raw sessions inside the Git-ignored `captures/` directory.

```sh
umask 077
python3 scripts/capture_hci_session.py --serial PHONE_SERIAL --output captures/SESSION
```

Choose a fresh output directory. To finish, press Ctrl-C or create a file named `STOP` in the session directory while the phone is connected. The collector takes a final snapshot and writes a SHA-256 manifest. Check `capture-events.jsonl` for errors and possible rotation gaps before interpreting an update trace.

## Mac firmware preflight

Run `./scripts/g2-preflight` to test the build 2279 About-label image offline. Use `--ota FILE` and `--image FILE` to select files. Exit 0 identifies the exact stock AP image, exit 2 identifies the exact label edit outside the stock manifest, and exit 1 indicates an input error or unexpected changes. This command reads local files only.
