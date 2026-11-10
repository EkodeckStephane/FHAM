import numpy as np

from fham.ecc import repetition_decode, repetition_encode
from fham.experiments import (
    EXTENDED_TRANSFORMS,
    GEOMETRIC_TRANSFORMS,
    assignment_method_comparison_experiment,
    causal_codebook_ablation_experiment,
    descriptor_comparison_experiment,
    ecc_repetition_experiment,
    extended_transformation_robustness_experiment,
    formulation_comparison_experiment,
    leakage_experiment,
    message_family_experiment,
    stability_aware_lambda_sweep_experiment,
    traffic_detectability_experiment,
)


def _tiny_image():
    return np.arange(48 * 48, dtype=np.uint16).reshape(48, 48).astype(np.uint8)


def test_descriptor_comparison_experiment_covers_all_families():
    images = {"tiny": _tiny_image()}
    summary, raw = descriptor_comparison_experiment(images, lengths=(5,), trials=1)
    assert set(summary["descriptor"]) == {"spectral", "dct_ordinal", "wavelet_gradient"}
    assert {"success", "mean_displacement", "b_star_median"}.issubset(summary.columns)


def test_formulation_comparison_experiment_costs_agree_when_feasible():
    images = {"tiny": _tiny_image()}
    _, raw = formulation_comparison_experiment(images, lengths=(5,), trials=1, bound=255)
    matches = raw["costs_match"].dropna()
    assert not matches.empty
    assert (matches == 1).all()


def test_assignment_method_comparison_includes_all_baselines():
    images = {"tiny": _tiny_image()}
    summary, _ = assignment_method_comparison_experiment(
        images, bound=8, lengths=(5,), trials=1
    )
    assert set(summary["method"]) == {
        "exact_matching",
        "greedy",
        "global_l1",
        "bottleneck",
        "random_feasible",
        "stability_aware",
    }


def test_stability_aware_lambda_sweep_reports_every_lambda():
    images = {"tiny": _tiny_image()}
    summary, _ = stability_aware_lambda_sweep_experiment(
        images, length=5, trials=1, bound=255
    )
    assert list(summary["lambda"]) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_leakage_experiment_reports_length_leakage_metrics():
    images = {"tiny": _tiny_image()}
    summary, raw = leakage_experiment(
        images, lengths=(5, 10), trials=2, size_class_bytes=64, bound=255
    )
    assert not raw.empty
    assert set(summary["envelope_mode"]) == {"compact", "shaped"}
    row = summary.loc[summary["envelope_mode"] == "compact"].iloc[0]
    assert row["distinct_lengths"] == 2
    assert -1.0 <= row["pearson_length_vs_raw_size"] <= 1.0
    assert row["mutual_info_length_vs_raw_size_bits"] >= 0.0
    shaped = summary.loc[summary["envelope_mode"] == "shaped"].iloc[0]
    assert shaped["distinct_raw_sizes"] == 1
    assert shaped["mutual_info_length_vs_raw_size_bits"] == 0.0


def test_causal_codebook_ablation_covers_all_codebooks_and_omits_incompatible_cell():
    images = {"tiny": _tiny_image()}
    summary, _ = causal_codebook_ablation_experiment(
        images, length=3, trials=1, bound=255
    )
    assert set(summary["codebook"]) == {
        "spectral",
        "dct_ordinal",
        "wavelet_gradient",
        "abdulsattar_arr4",
    }
    fham_strategies = set(
        summary.loc[summary["codebook"] == "spectral", "strategy"]
    )
    assert fham_strategies == {
        "exact_matching",
        "bounded_global_l1",
        "unbounded_global_l1",
        "stability_aware",
    }
    abdulsattar_strategies = set(
        summary.loc[summary["codebook"] == "abdulsattar_arr4", "strategy"]
    )
    assert abdulsattar_strategies == {
        "exact_matching",
        "bounded_global_l1",
        "unbounded_global_l1",
    }
    assert "stability_aware" not in abdulsattar_strategies


def test_extended_transformation_robustness_covers_36_conditions_plus_identity():
    images = {"tiny": _tiny_image()}
    summary, raw = extended_transformation_robustness_experiment(
        images, length=5, trials=1, bound=255
    )
    assert len(EXTENDED_TRANSFORMS) == 36
    assert set(summary["transform"]) == set(EXTENDED_TRANSFORMS) | {"identity"}
    identity_row = summary.loc[summary["transform"] == "identity"].iloc[0]
    assert identity_row["exact_recovery"] == 1.0


def test_traffic_detectability_reports_all_classifiers_and_baseline():
    image = np.arange(96 * 96, dtype=np.uint16).reshape(96, 96).astype(np.uint8)
    images = {"a": image, "b": np.roll(image, 7)}
    summary, raw = traffic_detectability_experiment(
        images, lengths=(5, 10), trials=10, bound=255
    )
    assert set(summary["classifier"]) == {
        "logistic_regression",
        "random_forest",
        "gradient_boosting",
        "mlp",
        "random_baseline",
    }
    assert set(summary["envelope_mode"]) == {"compact", "shaped"}
    assert set(raw["envelope_mode"]) == {"compact", "shaped"}
    assert set(raw["label"]) == {0, 1}
    baseline = summary.loc[
        (summary["envelope_mode"] == "compact")
        & (summary["classifier"] == "random_baseline")
    ].iloc[0]
    assert baseline["auc"] == 0.5


def test_message_family_experiment_reads_real_manifest():
    images = {"tiny": _tiny_image()}
    _, raw = message_family_experiment(images)
    assert set(raw["family"]) == {
        "uniform_bytes",
        "printable_ascii",
        "natural_text",
        "adversarial_repeated",
    }
    assert set(raw["length"]) == {10, 50, 100, 200, 400, 800, 1200, 1600}


def test_repetition_encode_decode_roundtrip_without_noise():
    message = "Hello, FHAM!"
    for repeat in (1, 3, 5):
        expanded = repetition_encode(message, repeat)
        assert len(expanded) == len(message) * repeat
        assert repetition_decode(expanded, len(message), repeat) == message


def test_repetition_decode_corrects_a_minority_of_corrupted_copies():
    expanded = list(repetition_encode("AB", 5))
    expanded[0] = "X"
    expanded[1] = "X"
    assert repetition_decode("".join(expanded), 2, 5) == "AB"


def test_ecc_repetition_experiment_covers_all_repeats_and_domains():
    images = {"tiny": _tiny_image()}
    summary, raw = ecc_repetition_experiment(
        images, repeats=(1, 3), length=4, trials=1, bound=255
    )
    assert set(summary["repeat"]) == {1, 3}
    assert set(summary["domain"]) == {"identity", "value", "geometric"}
    assert set(raw["transform"]) == set(EXTENDED_TRANSFORMS) | {"identity"}
    geometric_rows = raw.loc[raw["transform"].isin(GEOMETRIC_TRANSFORMS)]
    assert set(geometric_rows["domain"]) == {"geometric"}
    identity_rows = summary.loc[summary["domain"] == "identity"]
    assert (identity_rows["exact_recovery"] == 1.0).all()
