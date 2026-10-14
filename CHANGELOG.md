# Changelog

All notable changes to this project will be documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Public repository

This public tree starts from evaluation commit
`869722939d1695c27d28dd3b742af701f0a8e92f` (`8697229`). It was exported as a
fresh tree without the development history. Changes compared with that commit:

#### Removed

- An internal handoff note from the development repository.
- `docs/EXECUTION_PLAN.md`, an internal planning document.
- `docs/ROADMAP.md`, internal planning notes. The Planned list below remains.
- `docs/SYSTEM_CARD_QWEN35_9B.md`, a card for an earlier 0.1.1 development run.
  The published methods-beta results come from the later suite 0.2.0 runs.

#### Added

- `releases/v0.1-methods-beta/receipts.json` and `receipts.sha256`, the
  sanitized methods-beta receipts, byte-identical to the copies on the project
  page (SHA-256
  `e4a67010253a43ba270f704a5d334ad7b557b34bba83267fa8de3f490fbf644c`).
- `releases/v0.1-methods-beta/README.md`, describing the receipts, the primary
  run ID, the checksum and the CC BY 4.0 license.
- `.github/workflows/ci.yml`, which runs `uv sync --locked --extra dev` and
  `uv run pytest` on Python 3.12, then builds the wheel and checks that the
  installed `barl` command starts. It uses read-only permissions and actions
  pinned to full commit SHAs.

#### Changed

- `README.md`: renamed the project "Arabic Agent Reliability Lab by
  Bayanat Labs" and replaced the opening description of the repository with a
  "What is in v0" section. Added the project page link, a note that
  `barl doctor` warns about Ollama until a local service runs, the methods-beta
  results with their caveats, reproducibility details, a provenance note,
  license, citation and contact sections, and the standard About Bayanat Labs
  footer. Added a note on setting `BARL_ROOT` when the package is installed
  with pip. Removed the link to the removed system card and the mention of the
  execution plan, moved the trace verification commands to the Reproducibility
  section, renamed "What the benchmark measures" to "What the grader checks",
  and replaced the em dashes.
- `NOTICE`: the project name is now "Arabic Agent Reliability Lab by
  Bayanat Labs", and the trademark sentence now covers every data license in
  the repository, including the receipts.
- `SCENARIO_LICENSE.md`: the requested attribution now reads "Arabic Agent
  Reliability Lab by Bayanat Labs" and no longer uses an em dash.
- `CITATION.cff`: the title is now "Arabic Agent Reliability Lab". Added
  `repository-code`, pointed `url` at the project page, rewrote the abstract to
  match the repository description, and removed the `preferred-citation` block,
  which repeated the software entry.
- `docs/BENCHMARK_SPEC.md`: replaced 24 em dashes with colons, parentheses or
  commas, and updated the local-configurations row to cover more than one
  Ollama model. The wording is otherwise unchanged.
- `docs/DATA_GOVERNANCE.md`: replaced the em dash in the title. Nothing else
  changed, including the release gate.
- `docs/DATASET_CARD.md`: the project name is now "Arabic Agent Reliability Lab
  by Bayanat Labs", and reports go to hello@bayanatlabs.com.
- `docs/LICENSE_INVENTORY.md`: added a row for the methods-beta receipts
  (CC BY 4.0).
- `pyproject.toml`: removed the duplicate wheel force-include block so the
  package builds. Dependencies and `uv.lock` are unchanged.
- `.gitignore`: also ignores build output (`dist/`, `build/`) and macOS
  metadata (`.DS_Store`).

#### Unchanged

- `src/`, `tests/`, `scenarios/open/v0.json` (suite SHA-256
  `4a4286143a7b382d6ed745840096ede216211ebacfe489a1306d8e4e998081c7`),
  `scenarios/heldout/README.md`, `uv.lock`, `LICENSE`, `.python-version`, the
  `artifacts/` placeholders, and the earlier entries in this changelog.

### Changed

- Split operational state/action completion from deterministic communication
  checks. Response-check severity no longer changes the operational outcome.
- Replaced the all-family forbidden-action denominator with opportunity-aware
  reporting: unavailable by construction, available, proposed, blocked,
  execution error, and executed.
- Added recorded `least_privilege` and `full_toolset` modes so prohibited-tool
  selection can be evaluated without mislabeling permission boundaries as agent
  behavior.
- Replaced the unevaluable seller-note case with a guaranteed pre-decision
  untrusted-context exposure and a paired benign control.
- Expanded repeated-attempt reporting to outcome, operational result, final
  state, canonical tool trajectory, communication-assertion vector, and a
  documented lexical response normalization.
- Clarified that trace replay re-executes recorded tool calls; it does not
  reproduce model decisions or prove model determinism.
- Made the standalone Reliability Passport English-first while retaining the
  original Arabic methodology notices in an expandable section.
- Added plain-English failure explanations, attempt numbers, confidence-interval
  context, and direct links to each episode's trace and result receipt.

### Planned

- Independent, dialect-matched review of Saudi-oriented colloquial scenarios.
- A preregistered, full-suite local-model evaluation after the suite and adapter
  are frozen.
- Held-out evaluation governance before any official held-out score is released.

## [0.1.1] - 2026-08-05

### Changed

- Declared finite API values as JSON Schema enums so the model sees the actual
  tool contract instead of guessing hidden canonical strings.
- Enforced those enums at the sandbox boundary.
- Accepted equivalent natural Saudi-oriented status and date phrasing in two
  response-fact checks while retaining the operational grounding requirements.
- Kept exact response wording for partial returns as an interaction diagnostic;
  successful tool calls and final state remain the primary result.

### Evidence

- Preserved the initial 0.1.0 full-model development run rather than rewriting
  its result after these measurement defects were discovered.

## [0.1.0] - 2026-08-05

### Added

- Twenty open synthetic commerce workflows: ten MSA and ten Saudi-oriented
  colloquial examples labeled as unvalidated.
- A resettable local commerce sandbox with scenario-specific tool allowlists.
- State-, action-, policy-, and safety-based grading with repeated-run support.
- A deterministic rule-based regression control and a strict-JSON Ollama adapter.
- Hash-chained JSONL traces, JSON/HTML Reliability Passports, replay checks, and
  a local RTL dashboard.
- Benchmark specification, data governance, dataset and system cards, licensing
  inventory, citation metadata, and release documentation.

### Research status

- This release is an engineering and methodology preview. It does not publish a
  representative leaderboard, dialect-validity claim, certified threshold, or
  official held-out result.
