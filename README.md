# FHAM

Reproducible implementation, tests, datasets manifests, and experimental
results for the formal bounded-assignment FHAM model.

> FHAM: A Formal Bounded Assignment Model for Intra-Cover Hash Mapping

FHAM formulates intra-cover coverless-steganography mapping as a bounded
injective assignment between message symbols and hash-indexed cover
locations: an exact Hall-type condition characterizes feasibility, and a
rectangular linear assignment achieves the global $L_1$-optimal displacement,
proved equivalent to an aggregated min-cost-flow formulation. The repository
claims a formal assignment model and optimization layer; it does not claim a
complete, robust, end-to-end coverless communication protocol.

**This repository contains the reproducible artefact only** (code, tests,
configuration, dataset manifests, generated figures, and raw/processed
results). The manuscript itself (in its several venue-specific versions) is
maintained and submitted separately and is not included here.

## Reproducing the results

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python run_pipeline.py
```

`run_pipeline.py` regenerates all CSV results and figures under `results/`
and `paper/fig_*.png` from the exact preprocessed image corpus under
`dataset/`. Heavier, external-corpus validation stages
(`scripts/select_descriptor.py`, `scripts/run_stratified_robustness.py`,
`scripts/prepare_datasets.py`) require BOSSBase 1.01, BOWS2, and COCO 2017
validation to be available locally (see `dataset/README.md` and
`config/experiments.yaml` for the expected environment variables).

## Layout

- `src/fham/` — descriptors, assignment algorithms, channel, baselines
  (Abdulsattar, WYSAWIS), experiment definitions.
- `tests/` — unit and integration tests (`python -m pytest -q`).
- `scripts/` — dataset preparation, message generation, reference audit,
  experiment registry, descriptor selection, stratified robustness, paper
  compilation helpers.
- `config/experiments.yaml` — central experiment registry (descriptors,
  assignment methods, message families/lengths, bounds, transforms).
- `dataset/` — controlled and stress image corpora (with manifests) and the
  deterministic message manifest; external corpora are referenced by
  manifest and SHA-256 hash rather than redistributed.
- `results/` — raw and processed experimental results (CSV/JSON) underlying
  every table and figure in the manuscript.
- `reports/` — generated integrity report, acceptance gate, and experiment
  inventory.
- `references/` — bibliographic audit trail (offline checks and online
  Crossref verification).
