# Data governance and release policy (v0)

> Status: engineering and research preview. This document is operational guidance, not legal advice.

## Scope and permitted claims

Results apply only to the included scenarios and language conditions, the recorded system snapshot, and the documented scoring version. v0 does not measure Arabic ability comprehensively, certify a vendor or deployment, establish regulatory compliance, or prove production safety.

Public claims must identify the task, language condition, system configuration, metric, sample count, and uncertainty. Do not use “best Arabic model,” “certified,” “safe,” or population-level dialect claims from this development set.

## Systems, not model names

The evaluated object is a whole-system snapshot: weights and revision, tokenizer/chat template, quantization, inference runtime, prompts, decoding settings, context, tools, guardrails, hardware, and benchmark version. Provider-side or configuration changes create a new system snapshot.

## Synthetic-only v0

All v0 people, identifiers, addresses, products, orders, payments, and conversations are fictional. No customer, applicant, scraped social-media, or private communication data is allowed. Records carry origin, review, dialect-label, license, creation, and split metadata.

Synthetic text must never be presented as human-authored. It may validate schemas, action fidelity, safety rules, and coverage hypotheses. Without human review it cannot support claims about authentic dialect, cultural preference, natural register, or community norms.

## Dialect status

The Saudi-oriented prompts are synthetic and labeled `unvalidated_native_review_required`. They are exploratory diagnostics only, are excluded from authenticity claims, and must not be described as gold dialect data.

Official dialect-level claims require dialect-matched native reviewers, a written rubric, reviewer calibration, disagreement tracking, and adjudication. A language label describes evidence in one item; it does not infer an author's nationality, ethnicity, or identity.

## Privacy and safety

Public artifacts must pass automated and manual scans for personal data, secrets, and accidentally redistributed source content. Sensitive safety cases use the minimum operational detail needed to reproduce a finding. The benchmark must not be used as a standalone moderation or production-safety system.

Before incorporating human contributors, publish consent, compensation, retention, withdrawal limits, intended uses, sensitive-content protections, and a working correction/takedown contact.

## Leakage controls

The open split is for learning, integration testing, and development scores. Training, tuning, or prompt optimization on it is permitted by its license but must be disclosed with any result.

Future official held-out material is excluded from the open-data license and must not be used to train, retrieve, select prompts/checkpoints, repeatedly debug failures, reconstruct keys, or publish private cases. Before evaluation, store a cryptographic commitment to the held-out manifest. Confirmed leakage retires the affected version and triggers rotation and re-evaluation.

## Scoring interpretation

Reports distinguish deterministic rule metrics, model-assisted judgments, native human judgments, and exploratory diagnostics. LLM-as-judge output is never represented as native judgment. Aggregate scores must not conceal material safety, register, or task-family failures.

## Licensing

- Source code and harness configuration: Apache-2.0 unless stated otherwise.
- Rights-cleared open scenario data: CC BY 4.0, as identified by `SCENARIO_LICENSE.md`.
- Excluded: held-out material, third-party datasets, model weights/tokenizers, provider-governed outputs, trademarks, personal data, and confidential/customer material.

Every public release requires a license inventory, complete Apache `LICENSE` and notices, immutable version tag, checksummed manifest, dataset card, a disclosed system snapshot for every reported system, and changelog.

## Release gate

The methods beta (the v0.1 receipts and this repository) is published as an engineering preview under the limits stated in README.md. An official benchmark result, a held-out score, or any dialect claim is no-go until:

- all headline claims map to reproducible results and disclose uncertainty;
- clean-machine tests and local replay pass;
- every scenario has provenance, license, review, and split metadata;
- dialect-authenticity claims have qualified native review and adjudication;
- rights, privacy, secrets, and safety reviews pass;
- open and held-out materials are physically separated;
- methodology and limitations are published in Arabic and English;
- domain, email, repository, model-hub, correction, and takedown contacts work;
- a named release owner signs the final go/no-go decision.

