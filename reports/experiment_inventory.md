# Experiment Inventory

Total raw-result files: 20
Total logged trials across all raw files: 17746
Declared parameter values never exercised in any raw file: 0

## Raw Result Files

| File | Trials | Distinct images | Distinct lengths | Distinct methods/descriptors |
|---|---|---|---|---|
| results/assignment_ablation_raw.csv | 320 | 8 | 4 | - |
| results/assignment_method_comparison_raw.csv | 1440 | 8 | 3 | 6 |
| results/auxiliary_channel_raw.csv | 400 | 8 | 5 | - |
| results/bounded_assignment_raw.csv | 1200 | 8 | 3 | - |
| results/capacity_raw.csv | 800 | 8 | 10 | - |
| results/causal_codebook_ablation_raw.csv | 1200 | 8 | 1 | - |
| results/comparative_robustness_raw.csv | 165 | 3 | - | 3 |
| results/descriptor_comparison_raw.csv | 720 | 8 | 3 | 3 |
| results/descriptor_selection_validation_raw.csv | 1500 | 100 | 1 | 3 |
| results/extended_robustness_raw.csv | 1480 | 8 | - | - |
| results/formulation_comparison_raw.csv | 160 | 8 | 4 | - |
| results/leakage_raw.csv | 400 | 8 | 5 | - |
| results/mapping_comparison_controlled_raw.csv | 120 | 8 | 3 | - |
| results/mapping_comparison_stress_raw.csv | 657 | 219 | 3 | - |
| results/message_family_coverage_raw.csv | 1280 | 8 | 8 | - |
| results/robustness_raw.csv | 280 | 8 | - | - |
| results/stability_lambda_sweep_raw.csv | 200 | 8 | - | - |
| results/stress_bounded_assignment_raw.csv | 2190 | 219 | 1 | - |
| results/stress_capacity_raw.csv | 1314 | 219 | 2 | - |
| results/traffic_detectability_raw.csv | 1920 | 8 | 3 | - |

## Declared-Parameter Coverage (config/experiments.yaml)

Parameters declared in the central experiment registry but never observed
in any raw result file are listed below; they are declared for future
extension and are not claimed as executed in the current manuscript.

| Parameter | Value | Exercised |
|---|---|---|
| descriptor | spectral | yes |
| descriptor | dct_ordinal | yes |
| descriptor | wavelet_gradient | yes |
| assignment_method | exact_matching | yes |
| assignment_method | greedy | yes |
| assignment_method | global_l1 | yes |
| assignment_method | bottleneck | yes |
| assignment_method | stability_aware | yes |
| assignment_method | random_feasible | yes |
| message_family | uniform_bytes | yes |
| message_family | printable_ascii | yes |
| message_family | natural_text | yes |
| message_family | adversarial_repeated | yes |
| message_length_bytes | 10 | yes |
| message_length_bytes | 50 | yes |
| message_length_bytes | 100 | yes |
| message_length_bytes | 200 | yes |
| message_length_bytes | 400 | yes |
| message_length_bytes | 800 | yes |
| message_length_bytes | 1200 | yes |
| message_length_bytes | 1600 | yes |
| bound | 0 | yes |
| bound | 1 | yes |
| bound | 2 | yes |
| bound | 4 | yes |
| bound | 8 | yes |
| bound | 16 | yes |
| bound | 32 | yes |
| bound | 64 | yes |
| bound | 128 | yes |
| bound | 255 | yes |
| lambda | 0.0 | yes |
| lambda | 0.25 | yes |
| lambda | 0.5 | yes |
| lambda | 0.75 | yes |
| lambda | 1.0 | yes |
| transform | identity | yes |
| transform | jpeg90 | yes |
| transform | jpeg75 | yes |
| transform | resize90 | yes |
| transform | rotate1 | yes |
| transform | noise1 | yes |
| transform | noise2 | yes |
