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
| Protected envelope size at 200 bytes | Unbounded serialization sweep: compact 549.40 bytes (2.27x direct AES-GCM). Under the principal `B=2` assignment, a paired 80-message cohort is feasible in 80/80 cases and averages 549.88 bytes (2.27x direct). Traffic-shaped: fixed 852 bytes for all tested lengths up to 200 bytes. Direct AES-GCM is smaller in all these measurements. |
| Does the envelope leak message length? | Compact: yes, raw size carries the full 2.32 bits at 5 tested lengths and 64-byte classes still leak 1.92 bits. Traffic-shaped fixed-capacity envelopes reduce the tested size-only leakage to 0.00 bits |
| Robustness to transformations | Fixed-coordinate extraction from transformed pixels reaches no exact recovery across the 36-condition matrix. A separate closed-set pilot identifies 8/8 covers in a 219-image canonical gallery and recovers 40/40 messages per tested geometric transform using the retrieved canonical cover. |
| Authenticated session pilot | Across 40 records: session-key agreement, exact recovery, rejection of cover substitution, persistent replay rejection, and rejection of altered signed offers each succeed in 40/40 trials. |

## Security scope

FHAM leaves each cover's pixels unchanged. An image-only observer therefore
sees no per-image signal caused by pixel modifications during assignment.
An unchanged aggregate distribution of transmitted covers also requires
cover inclusion to be independent of message feasibility: selecting a cover
only after a successful assignment, or suppressing failed transmissions, can
make the observed cover distribution message-dependent. No image-only
steganalysis classifier is claimed here.

The assignment record is protected with AES-256-GCM. The current associated
The compact and shaped envelope baselines use a constant format label as
associated data. A separate session profile now binds AES-GCM authentication
to a canonical reference-image digest, a session identifier, and a sequence
number. It derives session keys from ephemeral X25519 exchanges, authenticates
key offers with Ed25519, and uses HKDF for key derivation. It requires the
peer identity public keys to be provisioned or pinned by the application. A
durable SQLite replay guard rejects duplicate and out-of-order records for
registered sessions. The pilot exercised key agreement, cover substitution,
altered offers, and replay rejection in 40/40 trials. It does not evaluate
identity-key compromise.

The reported H0/H1 classifier contrasts envelope-level features with
matched-shape decoys. A separate synthetic transport pilot generates raw-TCP
and TLS 1.3/TCP positive flows and scans reassembled TCP streams in the
available NonVPN captures. The custom application marker appears in all 80
raw-TCP positive flows and in none of the 80 TLS 1.3/TCP payload streams. Four
of 5,398 background TCP flows contain the unversioned four-byte `FHAM`
substring; none is a versioned candidate in the observed reassembled regions.
Three other background streams hit the parser's 1-MB pending-buffer cap, so
the latter result is limited to successfully reassembled regions.

For each synthetic profile and message length, flow size and packet count
individually fall within the central 10th--90th percentile range of the
background distributions. This marginal overlap is not a trained classifier
or an indistinguishability result. The background comprises labeled
application sessions captured with unrelated applications closed, not mixed
ordinary traffic. The positive captures are synthesized from controlled
software exchanges; the PCAPs in that pilot are synthesized. A second pilot
uses real loopback TCP sockets and a transparent byte-stream relay to compare
FHAM with HTTP/1.1 JSON controls of exactly matched request/response sizes.
Each transport profile has 240 pairs across three independent runs. On raw
TCP, the versioned FHAM marker appears in all 240 FHAM streams and in none of
the 240 controls. Under TLS 1.3, the marker appears in neither class; all 240
pairs have equal directional TLS record-length sequences and wire-byte totals.

A logistic-regression detector trained on two runs and tested on the third
gets AUC 0.500 from byte/record-size features. A detector using relay
read-chunk and timing features gets held-out AUCs of 0.461, 0.498, and 0.481
for raw TCP, and 0.514, 0.536, and 0.514 for TLS 1.3. All six paired-bootstrap
95% intervals include 0.50. Message length remains visible in total volume:
TLS client streams are 720 bytes at 40 characters and 1,360 bytes at 200.
These results measure a controlled local TCP-flow comparison against matched
HTTP controls. A separate detector comparison uses 1,946 TLS flows extracted
from 91 of the 109 captured NonVPN files. With each FHAM run and one third of
the background capture files held out by group, directional volume gives AUC
0.830--0.892, first-four-record lengths give 0.883--0.921, and combined
volume plus the first sixteen record lengths gives 0.957--0.986 (mean 0.976).
The result establishes detectability for this concrete FHAM endpoint and
framing against the available 2016 application-capture corpus. Matched HTTP
controls remain at AUC 0.50 because their directional sizes and record
sequences were matched to FHAM. Generalization to contemporary mixed-network
traffic and other TLS stacks remains open. See
[`reports/traffic_transport_pilot.md`](reports/traffic_transport_pilot.md) and
[`reports/socket_tls_detectability_pilot.md`](reports/socket_tls_detectability_pilot.md),
and [`reports/nonvpn_tls_detectability.md`](reports/nonvpn_tls_detectability.md).

The fixed-size record profile reduces the tested payload-size leakage; it is
not evidence of indistinguishability within ordinary network traffic.

The communication-size baseline also sets a clear limit on the claim: direct
AES-GCM transmission of the message is smaller than the measured FHAM records.
FHAM is evaluated for its fixed-cover assignment question—whether the
message's symbol multiplicities admit an injective bounded mapping, and the
minimum-cost mapping when feasible—not as a byte-efficient replacement for
direct encryption. Its controlled-codebook ablation shows the assignment
gain relative to exact hash matching; it does not establish an end-to-end
communication advantage over direct AES-GCM.

Geometric recovery is evaluated through transformed-pixel decoding and
canonical-cover retrieval. In the closed-set pilot, ORB/RANSAC identifies all
8 transformed query covers in a 219-image gallery for both tested attacks;
the receiver then recovers all 40 messages per attack from canonical copies.
Decoding the inverse-warped pixels themselves remains at 0/40 exact recovery.
The retrieval result depends on the correct canonical cover being present in
the gallery and does not measure open-set rejection or near-duplicate covers.

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
python -m pytest -q          # 32 tests, a few seconds
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

Focused revision experiments are also available:

```powershell
$env:PYTHONPATH = "src"
python scripts/measure_bounded_channel.py
python scripts/geometry_registration_pilot.py
python scripts/secure_channel_pilot.py
python scripts/traffic_transport_pilot.py --background D:\dataset --lengths 40 200 --trials-per-image 5
python scripts/matched_tls_control_pilot.py
python scripts/socket_tls_detectability_pilot.py --run-id rep1
python scripts/socket_tls_detectability_pilot.py --run-id rep2
python scripts/socket_tls_detectability_pilot.py --run-id rep3
python scripts/evaluate_socket_tls_generalization.py
```

The first measures paired compact-record and direct-encryption sizes for the
80-message, 200-character controlled cohort under `B=2`. The second runs an
exploratory ORB/RANSAC global-registration pilot for 1-degree rotation and
5% crop-restore and reports transformed-pixel recovery and closed-set canonical
cover retrieval. It identifies 8/8 query covers and recovers 40/40 messages
per condition from the 219-image gallery; recovery from warped pixels remains
0/40 exact. The secure-channel pilot runs the signed ephemeral key exchange,
cover binding, and persistent replay guard, then records both data and
amortized handshake sizes. The transport pilot generates 80 synthetic flows
per profile (raw TCP and TLS 1.3/TCP), checks exact application recovery, and
compares versioned marker visibility and marginal packet-count/flow-size ranges
with reassembled TCP flows from the NonVPN captures. Its detailed scope and
results are in `reports/traffic_transport_pilot.md`.

## Full reproduction and external datasets

### Non-VPN packet-marker baseline

When the ISCXVPN2016 non-VPN PCAP/PCAPNG files are available locally, reproduce
the packet-level signature baseline with:

```powershell
python scripts/analyze_nonvpn_traces.py D:\dataset --output results\nonvpn_trace_baseline.csv
python scripts/analyze_nonvpn_traces.py D:\dataset `
  --inspect-summary results\nonvpn_trace_baseline.csv `
  --marker-details results\nonvpn_marker_occurrences.csv
```

Reproduce the TCP stream and synthetic transport pilot with:

```powershell
python scripts/traffic_transport_pilot.py --background D:\dataset --lengths 40 200 --trials-per-image 5
```

This creates synthetic positive PCAPs and aggregate flow tables; it reads the
external NonVPN captures without copying packet payloads into the results.

The scan covers 109 labeled non-VPN application-session captures (21,919,108
packets). It found 30 `FHMS`, 8 `FHME`, and 7 `FHMT` packet-marker hits in 9
captures; none of the packet-local `FHMS` matches was followed by version byte
`0x01`. The four-byte markers collide with benign payload contents, while no
current `FHMS 0x01` candidate appeared in this packet-local scan. The dataset
contains targeted application sessions rather than mixed background traffic.
The scan has no FHAM-positive captures and does not measure stream reassembly,
flow/timing classification, or TLS-encapsulated FHAM traffic. The PCAP files are
not included here; obtain and cite the dataset from the [UNB CIC dataset
page](https://www.unb.ca/cic/datasets/vpn.html) and the originating study
(Draper-Gil et al., 2016, <https://doi.org/10.5220/0005740704070414>).

### FHAM TLS-flow detectability

Extract TLS record sequences from the captured NonVPN TCP flows and run the
capture-group-held-out classifier against the three live-socket FHAM runs:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --background D:\dataset
```

After extraction, rerun the four feature-set evaluations without rescanning the
PCAP files:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --reuse-extracted
```

The aggregate outputs are `results/nonvpn_tls_flow_features.csv` and
`results/nonvpn_tls_detectability_cv.csv`. The experiment reads the original
PCAP files in place and saves no packet payloads, addresses, or ports.

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

32 tests cover: exact round-trips, residual bounds, non-reuse of locations,
bounded infeasibility, dense/aggregated cost equivalence, exact `B*`
computation, AES-GCM tamper detection, nonce uniqueness, all three
descriptor families, the bottleneck/random-feasible/stability-aware
assignment methods, and each of the extension experiments added for the
causal ablation, leakage analysis, extended transformation matrix, and
message-manifest coverage.

## Reproducibility guarantees

> **Terminology note:** the experimental family stored internally as `natural_text` is templated natural-language text generated deterministically from a sentence template. The internal identifier is retained for backward compatibility with archived CSV files. The lambda sweep uses disjoint development and validation transformations; archived columns named `holdout_*` are legacy field names and do not denote an independent final test set.

- Quantitative table values and plotted measurements are generated from raw
  CSV/JSON files in this repository. Conceptual tables (such as the threat
  model and literature positioning) are maintained as structured manuscript
  tables and contain no experimental measurements.
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
  tested geometric transformation, and the compact envelope's message-length
  leakage before traffic shaping.

## Known limitations (by design)

- The spectral hash descriptor is **not** robust to geometric
  transformations (rotation, cropping) — this is measured and reported, not
  hidden.
- The compact auxiliary envelope leaks most message-length information
  through its raw size, even after fixed-class padding; the traffic-shaped
  envelope removes the tested size-only leakage at a substantial byte cost.
- The ISCXVPN2016 baseline checks packet-local marker collisions only. No
  FHAM-positive network traces, TCP-stream reassembly, flow/timing detection,
  TLS encapsulation, image-only steganalysis, or identity-key lifecycle and
  compromise study is included.
- Geometric catalog recovery is a closed-set result over the bundled 219-image
  stress catalog; open-set rejection and near-duplicate references remain to
  be measured.

## Authors

Habibatou Mindja, Ibrahima Touré, Stéphane Gaël R. Ekodeck, Serge Alain
Ebele, Leonel Moyou Metcheka, Daniel Tieudjo, René Ndoundam (corresponding author).

University of Yaoundé I (LIRIMA, Team GRIMCAPE); IRD, UMI UMMISCO, IRD
France Nord; UMI 209 UMMISCO, Sorbonne Université; Institut Supérieur des
Technologies de Mamou.

## License

See `LICENSE` in the repository root.
