# Dataset card: BARL RTL Commerce v0

## Summary

BARL RTL Commerce v0 is the open synthetic scenario pack shipped with the Arabic
Agent Reliability Lab by Bayanat Labs, version 0.2.0. It exercises Arabic
tool-using agents in one
fictional, resettable commerce environment. It is a small development suite for
harness engineering and qualitative failure discovery, not a representative
benchmark of Arabic speakers, dialects, commerce tasks, or deployed agents.

| Field | Value |
| --- | --- |
| Suite ID | `barl_rtl_commerce_v0` |
| Version | `0.2.0` |
| Split | Open development only |
| Records | 21 workflow scenarios |
| Registers | 10 MSA; 11 Saudi-oriented colloquial examples |
| Dialect review | Saudi-oriented examples are synthetic and unvalidated |
| Domain | Fictional retail support and commerce operations |
| Locale framing | Arabic, with an `ar-SA` product context |
| License | CC BY 4.0; see `SCENARIO_LICENSE.md` |

The authoritative record count and labels are the values in
`scenarios/open/v0.json`; validate them with `uv run barl validate` before use.

## Contents and task design

Each scenario declares an Arabic prompt, synthetic initial state, scenario policy,
allowed tools, step limit, expected state or action assertions, forbidden actions,
severity metadata, tags, and dialect-validation status. Security probes may also
declare a trust-labeled context item delivered before the first decision and
paired-condition metadata. Episodes cover patterns such as status lookup,
confirmation-gated mutations, cancellation and refund policy, privacy boundaries,
prompt injection in exposed seller-note context, ambiguity, unnecessary actions,
and escalation.

The grader evaluates observable tool calls and final sandbox state as the
operational layer. Natural-language responses are checked only where a scenario
explicitly declares a deterministic response requirement and are reported in a
separate communication layer; the suite is not a general Arabic generation
benchmark.

## Creation and provenance

Bayanat Labs authored the scenarios and fictional fixtures for this release. No
customer records, private conversations, social-media posts, or external text
corpus are represented. Names, identifiers, addresses, orders, products, and
policies are synthetic test fixtures. Record-level authorship and revision history
are not yet embedded in v0, so this card provides release-level provenance only.

The Saudi-oriented colloquial wording has not completed independent review by
dialect-matched native reviewers. Labels describe the authors' design intent, not
a validated linguistic classification. See `docs/DATA_GOVERNANCE.md` for the
review gate required before stronger claims.

## Intended uses

- Developing and regression-testing local agent harnesses and tool adapters.
- Inspecting failure traces for state mutation, confirmation, privacy, and policy
  behavior.
- Comparing frozen whole-system configurations on the same open suite while
  reporting uncertainty and full provenance.
- Teaching reproducible evaluation practices with fictional, inspectable data.

## Out-of-scope uses

- Claims about Arabic, Saudi, Gulf, or MSA performance in general.
- Linguistic quality, cultural authenticity, demographic, or sentiment research.
- Production safety certification, vendor ranking, procurement, or deployment
  approval based on v0 alone.
- Training or fine-tuning presented as independent evaluation on the same cases.
- Official held-out, blind, or contamination-resistant scoring; v0 has no
  distributed or official held-out set.
- Processing real customer data without a separate privacy and security review.

## Splits, leakage, and evaluation reporting

All 21 scenarios are public development cases. Prompts, fixtures, policies, tools,
and assertions are visible to system developers, so adaptation and leakage are
possible. A score on these cases must be labeled **open-suite development** and
must identify the suite version/hash, selected cases, attempts, source revision,
adapter, model digest, runtime, prompt hash, and generation settings. Do not call
it held out, blind, certified, or representative.

## Privacy and safety

The pack contains no intentionally real personal data. Some scenarios deliberately
contain synthetic privacy requests or adversarial instructions in order to test
agent behavior. They are not operational advice and must remain inside the local
sandbox. Report any accidentally real or rights-encumbered content by email to
[hello@bayanatlabs.com](mailto:hello@bayanatlabs.com). Do not include sensitive
material in a public issue or other public report.

## Known limitations

- Twenty-one cases in one fictional domain cannot estimate broad reliability.
- The 10/11 register allocation is a design choice caused by the paired security
  control, not a population sample or a dialect comparison.
- Dialect labels and naturalness lack independent validation.
- Public assertions invite overfitting and do not measure generalization.
- Default single attempts do not characterize stochastic stability.
- In least-privilege runs, most forbidden-rule tools may be unavailable by
  construction; those cases do not measure whether an agent would refuse the
  action if the tool were exposed.
- The sandbox omits voice, multimodal UI, browser, latency, long-horizon memory,
  production authorization, and real organizational constraints.
- Several checks depend on scenario-authored response requirements and policy
  interpretations that need external review.

## Maintenance and versioning

Material prompt, fixture, policy, assertion, tool, label, or review changes require
a suite-version change and changelog entry. Published results should retain the
exact suite SHA-256 rather than relying on the human-readable version alone.
Corrections should describe the affected scenario IDs and whether prior results
remain comparable.
