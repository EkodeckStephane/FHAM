import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from fham.config import PAPER_DIR, RESULTS_DIR
from fham.dataset import evaluation_images, standard_images
from fham.experiments import (
    assignment_ablation,
    assignment_method_comparison_experiment,
    bounded_assignment_experiment,
    capacity_experiment,
    causal_codebook_ablation_experiment,
    channel_experiment,
    codebook_geometry,
    comparative_mapping_experiment,
    comparative_robustness_experiment,
    descriptor_comparison_experiment,
    ecc_repetition_experiment,
    extended_transformation_robustness_experiment,
    formulation_comparison_experiment,
    leakage_experiment,
    message_family_experiment,
    robustness_experiment,
    stability_aware_lambda_sweep_experiment,
    stress_capacity_experiment,
    traffic_detectability_experiment,
)
from fham.visualization import (
    bounded_plot,
    capacity_plot,
    channel_plot,
    robustness_plot,
)


def save_pair(name, summary, raw):
    summary.to_csv(RESULTS_DIR / f"{name}.csv", index=False)
    raw.to_csv(RESULTS_DIR / f"{name}_raw.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["paper", "full"], default="paper")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.profile == "full":
        command = [sys.executable, "scripts/run_strict_pipeline.py"]
        if not args.strict:
            command = [sys.executable, "run_pipeline.py"]
        if args.strict:
            return subprocess.run(command, cwd=ROOT).returncode

    RESULTS_DIR.mkdir(exist_ok=True)
    images = standard_images()

    capacity, capacity_raw = capacity_experiment(images)
    save_pair("capacity", capacity, capacity_raw)
    capacity_plot(capacity, PAPER_DIR / "fig_capacity.png")

    ablation, ablation_raw = assignment_ablation(images)
    save_pair("assignment_ablation", ablation, ablation_raw)

    geometry = codebook_geometry(images)
    geometry.to_csv(RESULTS_DIR / "codebook_geometry.csv", index=False)

    channel, channel_raw = channel_experiment(images)
    save_pair("auxiliary_channel", channel, channel_raw)
    channel_plot(channel, PAPER_DIR / "fig_auxiliary_channel.png")

    bounded, bounded_raw = bounded_assignment_experiment(images)
    save_pair("bounded_assignment", bounded, bounded_raw)
    bounded_plot(bounded, PAPER_DIR / "fig_bounded_assignment.png")

    robustness, robustness_raw = robustness_experiment(images)
    save_pair("robustness", robustness, robustness_raw)
    robustness_plot(robustness, PAPER_DIR / "fig_robustness.png")

    stress_images = evaluation_images()
    stress, stress_raw = stress_capacity_experiment(stress_images)
    save_pair("stress_capacity", stress, stress_raw)

    stress_bounded, stress_bounded_raw = bounded_assignment_experiment(
        stress_images, lengths=(200,), trials=1
    )
    save_pair("stress_bounded_assignment", stress_bounded, stress_bounded_raw)

    stress_geometry = codebook_geometry(stress_images)
    stress_geometry.to_csv(
        RESULTS_DIR / "stress_codebook_geometry.csv", index=False
    )

    mapping_controlled, mapping_controlled_raw = comparative_mapping_experiment(
        images
    )
    save_pair("mapping_comparison_controlled", mapping_controlled, mapping_controlled_raw)

    mapping_stress, mapping_stress_raw = comparative_mapping_experiment(
        stress_images, trials=1
    )
    save_pair("mapping_comparison_stress", mapping_stress, mapping_stress_raw)

    comparative_robustness, comparative_robustness_raw = (
        comparative_robustness_experiment(images)
    )
    save_pair(
        "comparative_robustness",
        comparative_robustness,
        comparative_robustness_raw,
    )

    descriptor_comparison, descriptor_comparison_raw = descriptor_comparison_experiment(
        images
    )
    save_pair("descriptor_comparison", descriptor_comparison, descriptor_comparison_raw)

    formulation_comparison, formulation_comparison_raw = (
        formulation_comparison_experiment(images)
    )
    save_pair(
        "formulation_comparison", formulation_comparison, formulation_comparison_raw
    )

    assignment_method_comparison, assignment_method_comparison_raw = (
        assignment_method_comparison_experiment(images)
    )
    save_pair(
        "assignment_method_comparison",
        assignment_method_comparison,
        assignment_method_comparison_raw,
    )

    stability_lambda_sweep, stability_lambda_sweep_raw = (
        stability_aware_lambda_sweep_experiment(images)
    )
    save_pair(
        "stability_lambda_sweep", stability_lambda_sweep, stability_lambda_sweep_raw
    )

    message_family_coverage, message_family_coverage_raw = message_family_experiment(
        images
    )
    save_pair(
        "message_family_coverage",
        message_family_coverage,
        message_family_coverage_raw,
    )

    leakage, leakage_raw = leakage_experiment(images)
    save_pair("leakage", leakage, leakage_raw)

    causal_ablation, causal_ablation_raw = causal_codebook_ablation_experiment(images)
    save_pair("causal_codebook_ablation", causal_ablation, causal_ablation_raw)

    extended_robustness, extended_robustness_raw = (
        extended_transformation_robustness_experiment(images)
    )
    save_pair("extended_robustness", extended_robustness, extended_robustness_raw)

    traffic_detectability, traffic_detectability_raw = (
        traffic_detectability_experiment(images)
    )
    save_pair(
        "traffic_detectability", traffic_detectability, traffic_detectability_raw
    )

    ecc_repetition, ecc_repetition_raw = ecc_repetition_experiment(images)
    save_pair("ecc_repetition", ecc_repetition, ecc_repetition_raw)

    print(capacity.to_string(index=False))
    print()
    print(ablation.to_string(index=False))
    print()
    print(channel.to_string(index=False))
    print()
    print(bounded.to_string(index=False))
    print()
    print(robustness.to_string(index=False))
    print()
    print(stress.to_string(index=False))
    print()
    print(stress_bounded.to_string(index=False))
    print()
    print(mapping_controlled.to_string(index=False))
    print()
    print(mapping_stress.to_string(index=False))
    print()
    print(comparative_robustness.to_string(index=False))
    print()
    print(descriptor_comparison.to_string(index=False))
    print()
    print(formulation_comparison.to_string(index=False))
    print()
    print(assignment_method_comparison.to_string(index=False))
    print()
    print(stability_lambda_sweep.to_string(index=False))
    print()
    print(message_family_coverage.to_string(index=False))
    print()
    print(leakage.to_string(index=False))
    print()
    print(causal_ablation.to_string(index=False))
    print()
    print(extended_robustness.to_string(index=False))
    print()
    print(traffic_detectability.to_string(index=False))
    print()
    print(ecc_repetition.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
