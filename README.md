# FHAM — A Formal Bounded Assignment Model for Intra-Cover Hash Mapping

Reproducible implementation, tests, dataset manifests, and experimental
results underlying the FHAM manuscript.

**This repository contains the reproducible artefact only** (code, tests,
configuration, dataset manifests, generated figures, and raw/processed
results). The manuscript itself, is
maintained and submitted separately and is **not** included here.

## Table of contents

1. [What FHAM is](#what-fham-is)
2. [Key results](#key-results)
3. [Repository layout](#repository-layout)
4. [Installation](#installation)
5. [Quick start](#quick-start)
6. [Full reproduction and external datasets](#full-reproduction-and-external-datasets)
7. [Pipeline stages and scripts](#pipeline-stages-and-scripts)
8. [Tests](#tests)
9. [Reproducibility guarantees](#reproducibility-guarantees)
10. [Known limitations (by design)](#known-limitations-by-design)
11. [Authors](#authors)
12. [License](#license)

## What FHAM is

Mapping-based coverless image steganography represents a message by pointing
to intrinsic hash-indexed features of an unmodified cover image instead of
embedding bits into it. Exact-match designs (e.g., Abdulsattar's method)
require, for every message symbol, an *unused* cover location whose hash
equals that symbol's ASCII code exactly — which fails as soon as a code's
required multiplicity exceeds its availability in the cover.

FHAM (Flexible Hash-to-ASCII Mapping) reformulates this as a **bounded
injective assignment problem**:

- each message symbol must be assigned to a *distinct* cover location;
- the signed residual between the symbol and the assigned location's hash
  must satisfy `|delta| <= B` for a chosen bound `B`;
- subject to that bound, the assignment minimizing total `L1` residual is
  computed exactly by rectangular linear assignment (SciPy's
  Jonker-Volgenant solver);
- feasibility is characterized *exactly* by a Hall-type condition on the
  demand/capacity structure of the message and the cover's hash codebook;
- an equivalent aggregated formulation over the 256-value hash alphabet is
  solved by a min-cost-flow algorithm and proved (and empirically checked)
  to agree with the dense formulation on both cost and feasibility.

The auxiliary information needed to reconstruct the message (assigned
locations and residuals) is serialized, compressed, and protected with
AES-256-GCM before transport. The repository claims a formal assignment
model and optimization layer, together with an honestly measured auxiliary
channel; it does **not** claim a complete, robust, end-to-end covert
communication protocol, nor a novel robust image hash.

## Key results

All numbers below are produced by the pipeline in this repository from raw,
version-controlled results (`results/*.csv`, `results/*_raw.csv`); none are
hand-typed into the manuscript. See
[Reproducibility guarantees](#reproducibility-guarantees).

| Question | Result |
|---|---|
| Assignment success at 200 bytes, `B=2` | **100%** on 8 controlled images, **74.4%** on a 219-image stress corpus |
| Same protocol, Abdulsattar (exact match) | 0% / 0.46% |
| Same protocol, WYSAWIS cover adequacy | 37.5% / 50.7% |
| Is the gain from the assignment rule or the descriptor? | Causal ablation across 4 codebooks (3 descriptors + Abdulsattar's own): exact matching fails on **all four** (0%); switching only the assignment rule restores **92.5-100%** on all four |
| Which descriptor is used, and why? | Spectral descriptor selected by a fixed eligibility rule (success >= 99%, median `B*` <= 2, build time <= 2x baseline) on a disjoint 100-image BOSSBase validation sample, frozen before external test use |
| Protected envelope size at 200 bytes | 549 bytes (2.27x a directly AES-GCM-encrypted message of the same length) |
| Does the envelope leak message length? | Yes: raw envelope size carries the full 2.32 bits of length information at 5 tested lengths; 64-byte padding classes reduce this only to 1.92 bits — reported as a measured limitation, not hidden |
| Robustness to transformations | No non-identity condition (36-condition matrix: JPEG, resize, rotation, noise, filtering, photometric, crop, combined) reaches exact recovery; rotation and cropping are the most damaging. Confirmed at ~2000-images-per-corpus scale on BOSSBase, BOWS2, and COCO 2017 |

## Repository layout

```
FHAM/
├── src/fham/                    Python package
│   ├── descriptors.py           Spectral, DCT-ordinal, wavelet-gradient hash descriptors
│   ├── methods.py               Assignment methods (exact, greedy, bounded/global L1,
│   │                            bottleneck, random-feasible, stability-aware)
│   ├── assignment.py            Low-level solvers: dense, aggregated min-cost flow,
│   │                            bottleneck radius / B*, stability-aware cost
│   ├── channel.py                AES-256-GCM auxiliary-channel serialization
│   ├── abdulsattar.py            Abdulsattar (2021) baseline reimplementation
│   ├── wysawis.py                 WYSAWIS baseline reimplementation
│   ├── dataset.py                 Controlled / stress corpus loaders (scikit-image)
│   ├── config.py                  Shared constants and paths
│   └── experiments.py             All experiment functions (capacity, robustness,
│                                   causal ablation, leakage, message-family
│                                   coverage, descriptor comparison, ...)
├── tests/                        pytest suite (unit + integration)
├── scripts/
│   ├── prepare_datasets.py        Builds/validates BOSSBase, BOWS2, COCO 2017 manifests
│   ├── generate_messages.py       Deterministic 4-family x 8-length message manifest
│   ├── evaluate_benchmarks.py     Smoke/external benchmark over the 3 large corpora
│   ├── select_descriptor.py       Validation-gated descriptor selection (frozen decision)
│   ├── run_stratified_robustness.py  ~2000-images-per-corpus robustness check
│   ├── audit_references.py        Offline + online (Crossref) bibliography audit
│   ├── build_experiment_registry.py  Aggregates raw results into an experiment inventory
│   ├── write_provenance.py        Snapshots environment/config/git-state per run
│   ├── compile_paper.py           Manuscript compilation helper (not used by this repo)
│   ├── acceptance_gate.py         Pass/fail gate over required artefacts
│   └── run_strict_pipeline.py     Chains the stages above end to end
├── config/experiments.yaml        Central experiment registry (descriptors, assignment
│                                   methods, message families/lengths, bounds, transforms)
├── dataset/
│   ├── controlled/                8 standard scikit-image reference images + manifest
│   ├── stress/                    219-image stress corpus (incl. LFW faces) + manifest
│   ├── manifests/                 BOSSBase / BOWS2 / COCO 2017 manifests (SHA-256, splits)
│   ├── message_manifests/         160-message deterministic manifest (seeds, SHA-256)
│   └── messages/                  The 160 generated message files themselves
├── results/
│   ├── *.csv / *_raw.csv          Processed / raw results for every experiment
│   ├── raw/, processed/           Namespaced raw and processed outputs for larger runs
│   ├── provenance/<run_id>/       Environment, config, and git-state snapshot per run
│   └── acceptance/                Acceptance gate output, claim-evidence matrix,
│                                   frozen descriptor decision, experiment registry
├── reports/                       Generated integrity report, acceptance gate,
│                                   experiment inventory (all human-readable Markdown)
├── references/                    Bibliography audit trail (offline + online Crossref)
├── paper/                         Only `fig_*.png` and `cover/*.png` (generated figures
│                                   and dataset image copies) — the manuscript itself is
│                                   excluded from this repository, see `.gitignore`
├── run_pipeline.py                Main orchestrator (paper-scale experiments)
├── reproduce.ps1 / reproduce.sh   One-shot reproduction scripts (Windows / Unix)
├── requirements.txt               Python dependencies
└── pytest.ini
```

## Installation

Python 3.13 is used in development; NumPy 2.2+, SciPy 1.17+, pandas 2.3+,
Pillow 11+, scikit-image 0.25+, scikit-learn 1.7+, cryptography 45+, PyYAML
6+, matplotlib 3.10+, and pytest 8+ are required.

```powershell
python -m pip install -r requirements.txt
```

## Quick start

```powershell
python -m pytest -q          # 26 tests, a few seconds
python run_pipeline.py       # regenerates every CSV and figure used in the paper
```

`run_pipeline.py` runs entirely on the bundled `dataset/controlled` (8
images) and `dataset/stress` (219 images) corpora — no external download is
required for this quick path. It regenerates, among others: capacity,
bounded-assignment, comparative mapping (FHAM vs. Abdulsattar vs. WYSAWIS),
descriptor comparison, formulation equivalence (dense vs. aggregated flow),
extended assignment ablation, stability-aware lambda sweep, causal codebook
ablation, message-family coverage, message-length leakage, and the
36-condition extended transformation matrix.

## Full reproduction and external datasets

Three additional stages need large external image corpora that are **not**
bundled in this repository (only referenced by manifest and SHA-256 hash):

| Dataset | Expected images | Environment variable | Used by |
|---|---|---|---|
| BOSSBase 1.01 | 10,000 | `FHAM_BOSSBASE_DIR` | `select_descriptor.py`, `evaluate_benchmarks.py`, `run_stratified_robustness.py` |
| BOWS2 | 10,000 | `FHAM_BOWS2_DIR` | `evaluate_benchmarks.py`, `run_stratified_robustness.py` |
| COCO 2017 validation | 5,000 | `FHAM_COCO2017_DIR` | `evaluate_benchmarks.py`, `run_stratified_robustness.py` |

Set the environment variables to point at local copies of these public
datasets, then:

```powershell
python scripts/prepare_datasets.py --strict          # (re)builds dataset/manifests/*.csv
python scripts/select_descriptor.py                  # ~2 min; descriptor selection on BOSSBase validation
python scripts/evaluate_benchmarks.py                # smoke/external benchmark, ~60 images/corpus
python scripts/run_stratified_robustness.py           # ~1 hour; ~2000 images/corpus
python scripts/audit_references.py --online           # ~10 s; requires network access to Crossref
python scripts/build_experiment_registry.py
python scripts/acceptance_gate.py
```

or, for the fast stages only:

```powershell
powershell -ExecutionPolicy Bypass -File .\reproduce.ps1
```

## Pipeline stages and scripts

Every number reported anywhere in the manuscript is traceable to a script
and a raw result file — see `reports/experiment_inventory.md` (generated by
`scripts/build_experiment_registry.py`) for a full cross-reference between
declared parameters in `config/experiments.yaml` and the raw CSV files that
actually exercise them, and `results/acceptance/frozen_descriptor.json` /
`results/acceptance/claim_evidence_matrix.csv` for the descriptor-selection
decision and the claim-to-evidence audit trail.

## Tests

```powershell
python -m pytest -q
```

26 tests cover: exact round-trips, residual bounds, non-reuse of locations,
bounded infeasibility, dense/aggregated cost equivalence, exact `B*`
computation, AES-GCM tamper detection, nonce uniqueness, all three
descriptor families, the bottleneck/random-feasible/stability-aware
assignment methods, and each of the extension experiments added for the
causal ablation, leakage analysis, extended transformation matrix, and
message-manifest coverage.

## Reproducibility guarantees

- No numeric result is hand-typed into a table: every figure/table in the
  manuscript is generated from a raw CSV/JSON file present in this
  repository.
- Every experiment uses deterministic seeds (`config/experiments.yaml`,
  `RANDOM_SEED`); message content is generated once by
  `scripts/generate_messages.py` and reused identically across compared
  methods.
- `scripts/write_provenance.py` snapshots the environment, resolved
  configuration, and git commit for each pipeline run under
  `results/provenance/<run_id>/`.
- `scripts/acceptance_gate.py` fails the build if any required artefact
  (dataset manifests at the expected row count, reference audit, compiled
  claim-evidence matrix) is missing or inconsistent.
- Unfavorable results are reported rather than omitted: e.g., the
  wavelet-gradient descriptor's lower success rate, the random-feasible
  baseline's poor displacement, the absence of exact recovery under any
  tested geometric transformation, and the message-length leakage of the
  protected envelope.

## Known limitations (by design)

- The spectral hash descriptor is **not** robust to geometric
  transformations (rotation, cropping) — this is measured and reported, not
  hidden.
- The protected auxiliary envelope leaks most message-length information
  through its raw size, even after fixed-class padding.
- Traffic-analysis / detectability of the auxiliary channel (H0 vs. H1
  classifiers) and full reproducibility scaffolding (citation file,
  license, container image, locked environment) are tracked as ongoing
  work; see the repository's issue history for status.

## Authors

Habibatou Mindja, Ibrahima Touré, Stéphane Gaël R. Ekodeck, Serge Alain
Ebele, Leonel Moyou Metcheka, René Ndoundam (corresponding author).

University of Yaoundé I (LIRIMA, Team GRIMCAPE); IRD, UMI UMMISCO, IRD
France Nord; UMI 209 UMMISCO, Sorbonne Université; Institut Supérieur des
Technologies de Mamou.

## License

License to be added by the authors prior to first external release.
