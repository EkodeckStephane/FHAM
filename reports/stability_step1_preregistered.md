# FHAM Step 1: preregistered stability analysis

Date frozen: 2026-11-16
Branch: `revision/position-stability-2026-11-15`
Protocol source: `C:\Users\User\Downloads\FHAM — Protocole de l'étape 1 stabilité par position sous transformations.md`

## Scope and stop rules

This record freezes the analysis before validation or sealed-test image pixels are evaluated. Step 1 covers stability estimation, parameter selection, and geometric decoding diagnostics only. Error-correcting codes and Step 2 remain out of scope.

The article reproduction gate is first: reproduce Tables 8, 9, and 34 within 1 percentage point. Stop and diagnose any larger difference before proceeding. Validation transformations and sealed test images are not used to estimate stability. Scènes-11 is validation only. The sealed test is evaluated once, after the method and parameters are frozen.

The decision thresholds, transformation matrix, methods, decoding paths, metrics, sample-size rule, and statistical procedures are those in the supplied protocol (Sections 2–11). All results, including unfavorable results, are retained.

## Frozen data roles

- LFW-dev: deterministic 100-image subset for development stability and parameter fitting.
- LFW-val: the other 100 LFW images for configuration selection. These images are not an independent corpus from earlier FHAM capacity studies; that history will be disclosed. The stability-transform outcome metrics in Tables 8–9 are not reused as new validation evidence.
- Scènes-11: previously examined; external validation only.
- BOSSBase and COCO: 100 images per corpus, selected and hashed before pixel-level evaluation; one final execution after configuration freeze.

The contents of the supplied 400-image directories are not assumed to be independent of prior work. Their content hashes are matched against existing corpus manifests before test eligibility is asserted. Any overlap is excluded; if fewer than 100 eligible images remain in either corpus, the sealed-test size and corpus role must be revised before test execution.

## Scoring normalization discrepancy

The submitted implementation normalizes the residual by 255 (`src/fham/assignment.py::stability_aware_cost`). The supplied Step 1 protocol specifies normalization by B. These are not interchangeable: with the same lambda they change the relative weight of residual and stability. Table 8 reproduction therefore uses the submitted `/255` implementation. To keep the new S1–S4 comparisons internally controlled, all protocol variants use `/B`, and the legacy `/255` S1 reproduction is retained as a separate anchor. This implementation distinction is reported in the experiment provenance and manuscript methods; results from the two normalizations are never pooled.

## Frozen analysis choices

- Python executable: `C:\Users\User\AppData\Local\Programs\Python\Python313\python.exe`.
- Random seed root: `20261116`; preserve protocol's RANSAC seed `20261110`.
- Grouped unit for confidence intervals: image/cover; 10,000 cluster-bootstrap draws, percentile 95% intervals.
- Feasibility confidence intervals: Wilson 95% intervals.
- Paired method comparisons: Holm correction across the preregistered method × transform × path comparisons.
- Parameter choice: protocol rule, on LFW-val only; report all configurations and tie-breaking by lower D1.
- LFW image order: ascending SHA-256 of `20261116:<manifest image name>`; first 100 are dev, next 100 are validation; the first 20 dev covers form D0.
- Pilot `sd_Δ` uses per-cover paired character-accuracy differences P2−P1 for all three geometric validation transformations (rotation, crop, resize). The corrected 20-cover pilot has 19 feasible covers; the largest estimate is 201 covers (resize). LFW-val remains the preregistered 100 images for configuration selection; the sealed evaluation will use at least 201 eligible images in each corpus so the separately reported BOSSBase and COCO strata each meet that target.
- Receiver-only R-a threshold grid, fixed before validation: `z_flag ∈ {0.5, 1, 1.5, 2, 2.5, 3}`. Choose the threshold maximizing validation `R_max`; ties go to the smaller flagged fraction, then the larger threshold.
- Test pixels: remain sealed until the configuration, analysis code, and parameters are committed and frozen.

## D0 execution correction

The first stored D0 output did not apply P2 registration to resize-restoration, and failed registration could fall back to fixed-coordinate decoding. Those outputs are preserved under `results/stability_step1/pilot_d0_pre_resize_registration/` and are not used for inference. The authoritative D0 was rerun with ORB/RANSAC for rotation, crop-restoration, and resize-restoration; any failed registration is scored as a P2 failure. The corrected outputs and the three-geometry sample-size calculation are `pilot_d0_raw.csv`, `pilot_d0_summary.csv`, and `pilot_sample_size.json`.

## Required provenance artifacts

`results/stability_step1/` will contain protocol and script hashes, image manifests with SHA-256, software versions, exact commands, raw row-level results, aggregate tables, confidence intervals, and the final go/no-go page. Hash-only test-manifest creation is permitted before the final run; image decoding or model evaluation is not.
