# Integrity Report

Generated from `revision_ultime.md` on 2026-07-03 after the strict
infrastructure pass.

## Global Status

MANUSCRIT NON PRET POUR SOUMISSION

The project now contains the missing strict infrastructure requested in the
latest work session, but the strict acceptance gate cannot pass until BOWS2 and
COCO 2017 validation images are available locally or successfully downloaded.

## Implemented In This Pass

| Area | Artefacts |
|---|---|
| Descriptor families | `src/fham/descriptors.py` implements spectral, DCT ordinal, and wavelet-gradient descriptors |
| Assignment formulations | `src/fham/assignment.py` implements aggregated 256-value min-cost flow, dense cost comparison, B*, random feasible assignment, and stability-aware cost |
| Tests | `tests/test_strict_components.py`; full suite now has 15 passing tests |
| Strict config | `config/experiments.yaml` |
| Message generation | `scripts/generate_messages.py`; `dataset/message_manifests/message_seeds.csv` with 160 messages |
| Dataset manifests/download attempts | `scripts/prepare_datasets.py`; BOSSBase manifest has 10,000 rows |
| Benchmark smoke evaluation | `scripts/evaluate_benchmarks.py`; BOSSBase smoke outputs under `results/raw/benchmark_smoke` and `results/processed/benchmark_smoke` |
| Provenance layout | `scripts/write_provenance.py`; outputs under `results/raw`, `results/processed`, and `results/provenance` |
| Reference audit | `paper/references.bib`, `scripts/audit_references.py`, `references/*` |
| Supplement | `paper/supplement_fham.tex`, compiled to `paper/build/supplement_fham.pdf` |
| Strict reproduction | `reproduce.ps1`, `reproduce.sh`, and `python run_pipeline.py --profile full --strict` |
| Acceptance gate | `scripts/acceptance_gate.py`, `results/acceptance/acceptance_gate.json`, `reports/acceptance_gate.md` |

## Verification Run

| Check | Result |
|---|---|
| Unit tests | PASS: `15 passed` |
| BOSSBase manifest | PASS: 10,000 images from `C:\Users\User\Downloads\Compressed\cpu_stego_experiments\datasets\BOSSbase` |
| BOWS2 download | FAIL: DNS/download failed for the configured BOWS2 URL |
| COCO download | FAIL: download timed out; incomplete archive was removed |
| Reference audit | PASS offline metadata audit for 14 references |
| Article/supplement/cover compile | PASS into `paper/build/` |
| LaTeX fatal/undefined scan | PASS |
| Acceptance gate | FAIL only on BOWS2 and COCO manifests |

## Remaining Blocking Conditions

| Condition | Current Evidence | Required Action |
|---|---|---|
| BOWS2 evaluation | `dataset/manifests/bows2.csv` has 0 rows | Provide `FHAM_BOWS2_DIR` or allow a successful download of BOWS2 |
| COCO 2017 validation evaluation | `dataset/manifests/coco2017_val.csv` has 0 rows | Provide `FHAM_COCO2017_DIR` or allow a successful download of `val2017.zip` |

Once these datasets are available, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\reproduce.ps1
```

or:

```powershell
python run_pipeline.py --profile full --strict
```
