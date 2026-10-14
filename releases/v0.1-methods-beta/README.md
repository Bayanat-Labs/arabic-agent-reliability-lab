# Methods beta receipts (v0.1)

This folder holds the public evidence receipts for the methods beta of the
Arabic Agent Reliability Lab by Bayanat Labs. The same two files are published
on the [project page](https://www.bayanatlabs.com/research/arabic-agent-reliability),
and the copies here are byte-identical to them.

| File | Contents |
| --- | --- |
| `receipts.json` | Sanitized receipts for three selected synthetic cases, the disclosed system configurations and run IDs, and the limitations |
| `receipts.sha256` | The SHA-256 checksum of `receipts.json` |

## What the receipts are

`receipts.json` is a hand-curated, sanitized projection of selected synthetic
cases from development runs on 2026-08-05. It intentionally excludes raw traces,
private prompts, complete sandbox contents, and hidden evaluation material. All
cases are synthetic, open development cases in one fictional commerce sandbox.
The English renderings are editorial aids, not independently certified
translations.

| Item | Value |
| --- | --- |
| Release | `v0.1-methods-beta` |
| Primary run ID | `20260805T203152Z-ollama-local-strict-json-agent-2487fccc` |
| Evaluation commit | `869722939d1695c27d28dd3b742af701f0a8e92f` |
| Scenario suite | `barl_rtl_commerce_v0` 0.2.0, SHA-256 `4a4286143a7b382d6ed745840096ede216211ebacfe489a1306d8e4e998081c7` |
| Checksum of `receipts.json` | SHA-256 `e4a67010253a43ba270f704a5d334ad7b557b34bba83267fa8de3f490fbf644c` |

## Check the file

```console
shasum -a 256 receipts.json
cat receipts.sha256
```

Both commands must print the same hash. `receipts.sha256` holds the bare hash
without a file name, so compare the two values by eye or with a script rather
than with `shasum -c`.

## How to read them

The receipts describe disclosed whole-system configurations on a small open
synthetic suite. They are not a leaderboard or an accuracy score, and they do not
support claims about dialect performance, safety, certification, or production
readiness. Read the `limitations` field in `receipts.json` before repeating any
number. The repository [README](../../README.md#methods-beta-results) summarizes
the results with their caveats.

## License

`receipts.json` and `receipts.sha256`: Copyright 2026 Bayanat Labs. Licensed
under CC BY 4.0, the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode).

When sharing the receipts, use an attribution substantially equivalent to:

> Arabic Agent Reliability Lab by Bayanat Labs, methods beta receipts v0.1,
> run 20260805T203152Z-ollama-local-strict-json-agent-2487fccc, licensed CC BY 4.0.

Link to the CC BY 4.0 license and indicate whether changes were made. The
Bayanat Labs name and logo are not licensed.
