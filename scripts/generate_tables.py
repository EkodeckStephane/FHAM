from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUT_DIR = ROOT / "paper" / "tables" / "generated"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}\\%"


def write_table(
    name: str, colspec: str, rows: list[str], inputs: list[Path], commit: str
) -> None:
    # The generated file must be a complete, self-contained tabular
    # environment (not just toprule..bottomrule body rows) because
    # pdfTeX's alignment scanner does not reliably handle \input'd row
    # content nested inside a tabular wrapper kept in the including file:
    # \toprule/\bottomrule's lookahead breaks across the \input boundary
    # ("Misplaced \noalign" / "Extra }, or forgotten $." at \end{tabular}),
    # even though a bare \input of a *complete* tabular works fine.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = OUTPUT_DIR / f"{name}.tex"
    body = [f"\\begin{{tabular}}{{{colspec}}}"] + rows + ["\\end{tabular}"]
    tex_path.write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    provenance = {
        "script": "scripts/generate_tables.py",
        "table": name,
        "git_commit": commit,
        "input_files": [str(path.relative_to(ROOT)) for path in inputs],
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in inputs
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": str(tex_path.relative_to(ROOT)),
        "output_sha256": sha256(tex_path),
    }
    (OUTPUT_DIR / f"{name}.provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote {tex_path.relative_to(ROOT)} + provenance")


def table_assignment_ablation(commit: str) -> None:
    path = RESULTS / "assignment_ablation.csv"
    df = pd.read_csv(path)
    rows = ["\\toprule", "\\textbf{Length} & \\textbf{Greedy $D_1$} & \\textbf{Global $D_1$} & \\textbf{Greedy (ms)} & \\textbf{Global (ms)} \\\\", "\\midrule"]
    for _, row in df.iterrows():
        rows.append(
            f"{int(row['length'])} & {row['greedy_displacement']:.2f} & {row['optimal_displacement']:.2f} & "
            f"{row['greedy_ms']:.2f} & {row['optimal_ms']:.2f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_assignment_ablation", "rrrrr", rows, [path], commit)


def table_formulation_comparison(commit: str) -> None:
    path = RESULTS / "formulation_comparison.csv"
    df = pd.read_csv(path)
    rows = ["\\toprule", "\\textbf{Length} & \\textbf{Feasible} & \\textbf{Cost Agree.} & \\textbf{Dense (ms)} & \\textbf{Aggreg. (ms)} \\\\", "\\midrule"]
    for _, row in df.iterrows():
        rows.append(
            f"{int(row['length'])} & {pct(row['dense_feasible'])} & {pct(row['cost_agreement'])} & "
            f"{row['mean_dense_ms']:.2f} & {row['mean_aggregated_ms']:.2f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_formulation_comparison", "rrrrr", rows, [path], commit)


def table_extended_ablation(commit: str) -> None:
    path = RESULTS / "assignment_method_comparison.csv"
    df = pd.read_csv(path)
    display = {
        "exact_matching": "Exact matching (A1)",
        "greedy": "Greedy",
        "global_l1": "Global $L_1$",
        "bottleneck": "Bottleneck (A4)",
        "random_feasible": "Random feasible (A6)",
        "stability_aware": "Stability-aware",
    }
    order = ["exact_matching", "greedy", "global_l1", "bottleneck", "random_feasible", "stability_aware"]
    rows = [
        "\\toprule",
        "\\textbf{Method} & \\textbf{Length} & \\textbf{Success} & \\textbf{Mean $D_1$} & "
        "\\textbf{Mean Max $|\\delta|$} & \\textbf{Time (ms)} \\\\",
        "\\midrule",
    ]
    for method in order:
        subset = df[df["method"] == method].sort_values("length")
        for _, row in subset.iterrows():
            disp = "--" if pd.isna(row["mean_total_displacement"]) else f"{row['mean_total_displacement']:.2f}"
            maxd = "--" if pd.isna(row["mean_max_displacement"]) else f"{row['mean_max_displacement']:.2f}"
            rows.append(
                f"{display[method]} & {int(row['length'])} & {pct(row['success'], 2)} & {disp} & "
                f"{maxd} & {row['mean_time_ms']:.2f} \\\\"
            )
    rows.append("\\bottomrule")
    write_table("tab_extended_ablation", "lrrrrr", rows, [path], commit)


def table_stability_lambda(commit: str) -> None:
    path = RESULTS / "stability_lambda_sweep.csv"
    df = pd.read_csv(path)
    rows = [
        "\\toprule",
        "$\\boldsymbol{\\lambda}$ & \\textbf{Success} & \\textbf{Mean $D_1$} & \\textbf{Held-Out Exact} & \\textbf{Held-Out Acc.} \\\\",
        "\\midrule",
    ]
    for _, row in df.iterrows():
        rows.append(
            f"{row['lambda']:.2f} & {pct(row['success'])} & {row['mean_total_displacement']:.2f} & "
            f"{pct(row['holdout_exact_recovery'])} & {pct(row['holdout_character_accuracy'])} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_stability_lambda", "rrrrr", rows, [path], commit)


def table_causal_ablation(commit: str) -> None:
    path = RESULTS / "causal_codebook_ablation.csv"
    df = pd.read_csv(path)
    codebook_display = {
        "abdulsattar_arr4": "Abdulsattar Arr.4",
        "spectral": "Spectral (D0)",
        "dct_ordinal": "DCT ordinal (D1)",
        "wavelet_gradient": "Wavelet-grad. (D2)",
    }
    strategy_display = {
        "exact_matching": "Exact matching",
        "bounded_global_l1": "Bounded $L_1$ ($B{=}2$)",
        "unbounded_global_l1": "Unbounded global $L_1$",
        "stability_aware": "Stability-aware",
    }
    codebook_order = ["abdulsattar_arr4", "spectral", "dct_ordinal", "wavelet_gradient"]
    strategy_order = ["exact_matching", "bounded_global_l1", "unbounded_global_l1", "stability_aware"]
    rows = [
        "\\toprule",
        "\\textbf{Codebook} & \\textbf{Strategy} & \\textbf{Success} & \\textbf{Mean $D_1$} \\\\",
        "\\midrule",
    ]
    for codebook in codebook_order:
        for strategy in strategy_order:
            match = df[(df["codebook"] == codebook) & (df["strategy"] == strategy)]
            if match.empty:
                continue
            row = match.iloc[0]
            disp = "--" if pd.isna(row["mean_total_displacement"]) else f"{row['mean_total_displacement']:.2f}"
            rows.append(
                f"{codebook_display[codebook]} & {strategy_display[strategy]} & {pct(row['success'])} & {disp} \\\\"
            )
    rows.append("\\bottomrule")
    write_table("tab_causal_ablation", "llrr", rows, [path], commit)


def table_bounded_stress(commit: str) -> None:
    controlled_path = RESULTS / "bounded_assignment.csv"
    stress_path = RESULTS / "stress_bounded_assignment.csv"
    controlled = pd.read_csv(controlled_path)
    stress = pd.read_csv(stress_path)
    controlled_200 = controlled[controlled["length"] == 200].set_index("bound")
    stress_200 = stress[stress["length"] == 200].set_index("bound")
    bounds = sorted(set(controlled_200.index) & set(stress_200.index))
    rows = [
        "\\toprule",
        "$B$ & \\textbf{Controlled ASR (\\%)} & \\textbf{Stress ASR (\\%)} \\\\",
        "\\midrule",
    ]
    for bound in bounds:
        rows.append(
            f"{bound} & {controlled_200.loc[bound, 'success'] * 100:.1f} & "
            f"{stress_200.loc[bound, 'success'] * 100:.1f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_bounded_stress", "rrr", rows, [controlled_path, stress_path], commit)


def table_descriptor_comparison(commit: str) -> None:
    path = RESULTS / "descriptor_comparison.csv"
    df = pd.read_csv(path)
    rows = [
        "\\toprule",
        "& \\multicolumn{2}{c}{\\textbf{Spectral (D0)}} & \\multicolumn{2}{c}{\\textbf{DCT Ordinal (D1)}} & "
        "\\multicolumn{2}{c}{\\textbf{Wavelet-Gradient (D2)}} \\\\",
        "\\textbf{Length} & \\textbf{Success} & \\textbf{Mean $D_1$} & \\textbf{Success} & \\textbf{Mean $D_1$} & "
        "\\textbf{Success} & \\textbf{Mean $D_1$} \\\\",
        "\\midrule",
    ]
    for length in sorted(df["length"].unique()):
        cells = [str(int(length))]
        for descriptor in ("spectral", "dct_ordinal", "wavelet_gradient"):
            row = df[(df["length"] == length) & (df["descriptor"] == descriptor)].iloc[0]
            cells.append(pct(row["success"]))
            cells.append(f"{row['mean_displacement']:.2f}")
        rows.append(" & ".join(cells) + " \\\\")
    rows.append("\\bottomrule")
    write_table("tab_descriptor_comparison", "rrrrrrr", rows, [path], commit)


def table_descriptor_selection(commit: str) -> None:
    path = RESULTS / "descriptor_selection_validation.csv"
    frozen_path = RESULTS / "acceptance" / "frozen_descriptor.json"
    df = pd.read_csv(path)
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    eligible_by_descriptor = {
        candidate["descriptor"]: candidate["meets_success_threshold"]
        and candidate["meets_radius_threshold"]
        and candidate["meets_time_threshold"]
        for candidate in frozen["candidates"]
    }
    display = {
        "spectral": "Spectral (D0)",
        "dct_ordinal": "DCT ordinal (D1)",
        "wavelet_gradient": "Wavelet-gradient (D2)",
    }
    rows = [
        "\\toprule",
        "\\textbf{Descriptor} & \\textbf{Success} & \\textbf{Med. $B^\\ast$} & \\textbf{Build (ms)} & \\textbf{Eligible} \\\\",
        "\\midrule",
    ]
    for descriptor in ("spectral", "dct_ordinal", "wavelet_gradient"):
        row = df[df["descriptor"] == descriptor].iloc[0]
        eligible = "yes" if eligible_by_descriptor[descriptor] else "no"
        rows.append(
            f"{display[descriptor]} & {pct(row['success'])} & {row['b_star_median']:.1f} & "
            f"{row['mean_build_ms']:.1f} & {eligible} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_descriptor_selection", "lrrrc", rows, [path, frozen_path], commit)


def table_message_family(commit: str) -> None:
    path = RESULTS / "message_family_coverage.csv"
    df = pd.read_csv(path)
    display = {
        "uniform_bytes": "Uniform",
        "printable_ascii": "ASCII",
        "natural_text": "Natural",
        "adversarial_repeated": "Adversarial",
    }
    rows = [
        "\\toprule",
        "\\textbf{Length} & \\textbf{Uniform} & \\textbf{ASCII} & \\textbf{Natural} & \\textbf{Adversarial} \\\\",
        "\\midrule",
    ]
    for length in sorted(df["length"].unique()):
        cells = [str(int(length))]
        for family in ("uniform_bytes", "printable_ascii", "natural_text", "adversarial_repeated"):
            row = df[(df["length"] == length) & (df["family"] == family)].iloc[0]
            cells.append(pct(row["success"]))
        rows.append(" & ".join(cells) + " \\\\")
    rows.append("\\bottomrule")
    write_table("tab_message_family", "rrrrr", rows, [path], commit)


def table_channel_real(commit: str) -> None:
    path = RESULTS / "auxiliary_channel.csv"
    df = pd.read_csv(path)
    rows = [
        "\\toprule",
        "\\textbf{Length} & \\textbf{FHAM (B)} & \\textbf{Direct (B)} & \\textbf{Ratio} & \\textbf{Enc./Dec. (ms)} \\\\",
        "\\midrule",
    ]
    for _, row in df.iterrows():
        rows.append(
            f"{int(row['length'])} & {row['encrypted_bytes']:.2f} & {row['direct_encrypted_bytes']:.2f} & "
            f"{row['fham_to_direct_ratio']:.2f} & {row['encrypt_ms']:.2f}/{row['decrypt_ms']:.2f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_channel_real", "rrrrr", rows, [path], commit)


def table_leakage(commit: str) -> None:
    path = RESULTS / "leakage.csv"
    row = pd.read_csv(path).iloc[0]
    rows = [
        "\\toprule",
        "\\textbf{Quantity} & \\textbf{Value} \\\\",
        "\\midrule",
        f"Distinct lengths tested & {int(row['distinct_lengths'])} \\\\",
        f"Distinct raw envelope sizes & {int(row['distinct_raw_sizes'])} \\\\",
        f"Distinct padded size classes & {int(row['distinct_size_classes'])} \\\\",
        f"Pearson $r$(length, raw size) & {row['pearson_length_vs_raw_size']:.3f} \\\\",
        f"Pearson $r$(length, padded size) & {row['pearson_length_vs_padded_size']:.3f} \\\\",
        f"Mutual information(length; raw size) & {row['mutual_info_length_vs_raw_size_bits']:.2f} bits \\\\",
        f"Mutual information(length; size class) & {row['mutual_info_length_vs_size_class_bits']:.2f} bits \\\\",
        "\\bottomrule",
    ]
    write_table("tab_leakage", "lr", rows, [path], commit)


def table_traffic_detectability(commit: str) -> None:
    path = RESULTS / "traffic_detectability.csv"
    df = pd.read_csv(path)
    display = {
        "logistic_regression": "Logistic regression",
        "random_forest": "Random forest",
        "gradient_boosting": "Gradient boosting",
        "mlp": "MLP",
        "random_baseline": "Random baseline",
    }
    order = ["logistic_regression", "random_forest", "gradient_boosting", "mlp", "random_baseline"]
    rows = [
        "\\toprule",
        "\\textbf{Classifier} & \\textbf{AUC} & \\textbf{Bal. Acc.} & \\textbf{TPR@5\\%FPR} \\\\",
        "\\midrule",
    ]
    for classifier in order:
        row = df[df["classifier"] == classifier].iloc[0]
        rows.append(
            f"{display[classifier]} & {row['auc']:.2f} & {row['balanced_accuracy']:.2f} & "
            f"{row['tpr_at_5pct_fpr']:.2f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_traffic_detectability", "lrrr", rows, [path], commit)


def table_robustness(commit: str) -> None:
    path = RESULTS / "robustness.csv"
    df = pd.read_csv(path)
    display = {
        "identity": "Identity",
        "jpeg90": "JPEG quality 90",
        "jpeg75": "JPEG quality 75",
        "resize90": "Resize 0.9",
        "noise1": "Gaussian noise $\\sigma=1$",
        "noise2": "Gaussian noise $\\sigma=2$",
        "rotate1": "Rotation $1^\\circ$",
    }
    order = ["identity", "jpeg90", "jpeg75", "resize90", "noise1", "noise2", "rotate1"]
    rows = [
        "\\toprule",
        "\\textbf{Transformation} & \\textbf{Exact (\\%)} & \\textbf{Characters (\\%)} \\\\",
        "\\midrule",
    ]
    for attack in order:
        row = df[df["attack"] == attack].iloc[0]
        rows.append(
            f"{display[attack]} & {row['exact_recovery'] * 100:.0f} & {row['character_accuracy'] * 100:.1f} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_robustness", "lrr", rows, [path], commit)


def table_comparative_robustness(commit: str) -> None:
    path = RESULTS / "comparative_robustness.csv"
    df = pd.read_csv(path)
    display = {
        "identity": "Identity",
        "speckle005": "Speckle noise, $v=0.005$",
        "saltpepper005": "Salt-and-pepper, $v=0.005$",
        "gaussian_filter5": "Gaussian filter, $5\\times5$",
        "median_filter5": "Median filter, $5\\times5$",
    }
    attack_order = ["identity", "speckle005", "saltpepper005", "gaussian_filter5", "median_filter5"]
    methods = ["FHAM B=2", "Abdulsattar Arr.4", "WYSAWIS core"]
    rows = [
        "\\toprule",
        "\\textbf{Attack} & \\textbf{FHAM ($B=2$)} & \\textbf{Abdulsattar Arr.4} & \\textbf{WYSAWIS core} \\\\",
        "\\midrule",
    ]
    for attack in attack_order:
        cells = [display[attack]]
        for method in methods:
            row = df[(df["attack"] == attack) & (df["method"] == method)].iloc[0]
            cells.append(f"{row['bit_accuracy'] * 100:.1f}\\%")
        rows.append(" & ".join(cells) + " \\\\")
    rows.append("\\bottomrule")
    write_table("tab_comparative_robustness", "lrrr", rows, [path], commit)


EXTENDED_ROBUSTNESS_CATEGORIES = {
    "JPEG quality (5)": ["jpeg50", "jpeg75", "jpeg85", "jpeg90", "jpeg95"],
    "Resize-restore (4)": ["resize075", "resize090", "resize110", "resize125"],
    "Rotation (4)": ["rotate_neg1", "rotate_neg0_5", "rotate_pos0_5", "rotate_pos1"],
    "Gaussian noise (3)": ["gnoise_sigma0_5", "gnoise_sigma1", "gnoise_sigma2"],
    "Speckle noise (2)": ["speckle_v0_001", "speckle_v0_005"],
    "Impulse noise (2)": ["impulse_d0_001", "impulse_d0_005"],
    "Gaussian/median filter (4)": ["gfilter_k3", "gfilter_k5", "medfilter_k3", "medfilter_k5"],
    "Photometric (6)": [
        "brightness_neg10", "brightness_pos10", "contrast_neg10", "contrast_pos10", "gamma_0_9", "gamma_1_1",
    ],
    "Crop-restore (2)": ["crop_restore_1pct", "crop_restore_5pct"],
    "Combined (4)": [
        "combo_jpeg90_resize090", "combo_jpeg90_gnoise1", "combo_resize090_gfilter3", "combo_jpeg85_brightness_pos10",
    ],
}


def table_extended_robustness(commit: str) -> None:
    path = RESULTS / "extended_robustness.csv"
    df = pd.read_csv(path).set_index("transform")
    rows = [
        "\\toprule",
        "\\textbf{Category (conditions)} & \\textbf{Min (\\%)} & \\textbf{Max (\\%)} \\\\",
        "\\midrule",
    ]
    for category, transforms in EXTENDED_ROBUSTNESS_CATEGORIES.items():
        values = df.loc[transforms, "character_accuracy"] * 100
        rows.append(f"{category} & {values.min():.1f} & {values.max():.1f} \\\\")
    identity_value = df.loc["identity", "character_accuracy"] * 100
    rows.append(f"Identity (1) & \\multicolumn{{2}}{{c}}{{{identity_value:.1f}}} \\\\")
    rows.append("\\bottomrule")
    write_table("tab_extended_robustness", "lrr", rows, [path], commit)


def table_external_corpus(commit: str) -> None:
    path = RESULTS / "processed" / "benchmark_smoke" / "benchmark_assignment.csv"
    df = pd.read_csv(path)
    display = {
        "adversarial_repeated": "Adversarial repeated",
        "natural_text": "Natural text",
        "printable_ascii": "Printable ASCII",
        "uniform_bytes": "Uniform bytes",
    }
    families = ["adversarial_repeated", "natural_text", "printable_ascii", "uniform_bytes"]
    datasets = ["bossbase", "bows2", "coco2017_val"]
    rows = [
        "\\toprule",
        "& \\multicolumn{3}{c}{\\textbf{50 bytes (300 trials)}} & \\multicolumn{3}{c}{\\textbf{100 bytes (60 trials)}} \\\\",
        "\\textbf{Family} & \\textbf{BOSSBase} & \\textbf{BOWS2} & \\textbf{COCO2017} & \\textbf{BOSSBase} & "
        "\\textbf{BOWS2} & \\textbf{COCO2017} \\\\",
        "\\midrule",
    ]
    for family in families:
        cells = [display[family]]
        for length in (50, 100):
            for dataset in datasets:
                match = df[
                    (df["family"] == family)
                    & (df["message_bytes"] == length)
                    & (df["dataset"] == dataset)
                ]
                cells.append(pct(match.iloc[0]["success"]) if not match.empty else "--")
        rows.append(" & ".join(cells) + " \\\\")
    rows.append("\\bottomrule")
    write_table("tab_external_corpus", "lrrrrrr", rows, [path], commit)


def table_stratified_robustness(commit: str) -> None:
    path = RESULTS / "processed" / "stratified_robustness" / "stratified_robustness.csv"
    df = pd.read_csv(path)
    display = {
        "identity": "Identity",
        "jpeg90": "JPEG quality 90",
        "jpeg75": "JPEG quality 75",
        "resize090": "Resize 0.90",
        "rotate_pos1": "Rotation $1^\\circ$",
        "gnoise_sigma1": "Gaussian noise $\\sigma{=}1$",
        "gfilter_k3": "Gaussian filter $3\\times3$",
        "medfilter_k3": "Median filter $3\\times3$",
    }
    order = ["identity", "jpeg90", "jpeg75", "resize090", "rotate_pos1", "gnoise_sigma1", "gfilter_k3", "medfilter_k3"]
    datasets = ["bossbase", "bows2", "coco2017_val"]
    rows = [
        "\\toprule",
        "\\textbf{Transform} & \\textbf{BOSSBase} & \\textbf{BOWS2} & \\textbf{COCO2017} \\\\",
        "\\midrule",
    ]
    for transform in order:
        cells = [display[transform]]
        for dataset in datasets:
            row = df[(df["transform"] == transform) & (df["dataset"] == dataset)].iloc[0]
            cells.append(pct(row["character_accuracy"]))
        rows.append(" & ".join(cells) + " \\\\")
    rows.append("\\bottomrule")
    write_table("tab_stratified_robustness", "lrrr", rows, [path], commit)


def table_ecc_repetition(commit: str) -> None:
    path = RESULTS / "ecc_repetition.csv"
    df = pd.read_csv(path).set_index(["repeat", "domain"])
    rows = [
        "\\toprule",
        "\\textbf{Repeat} & \\textbf{Value exact (\\%)} & \\textbf{Value char.\\ acc.\\ (\\%)} & "
        "\\textbf{Geom.\\ exact (\\%)} & \\textbf{Geom.\\ char.\\ acc.\\ (\\%)} \\\\",
        "\\midrule",
    ]
    for repeat in sorted(df.index.get_level_values("repeat").unique()):
        value_row = df.loc[(repeat, "value")]
        geom_row = df.loc[(repeat, "geometric")]
        rows.append(
            f"{int(repeat)} & {pct(value_row['exact_recovery'])} & {pct(value_row['character_accuracy'])} & "
            f"{pct(geom_row['exact_recovery'])} & {pct(geom_row['character_accuracy'])} \\\\"
        )
    rows.append("\\bottomrule")
    write_table("tab_ecc_repetition", "rrrrr", rows, [path], commit)


def main() -> int:
    commit = git_commit()
    table_assignment_ablation(commit)
    table_formulation_comparison(commit)
    table_extended_ablation(commit)
    table_stability_lambda(commit)
    table_causal_ablation(commit)
    table_bounded_stress(commit)
    table_descriptor_comparison(commit)
    table_descriptor_selection(commit)
    table_message_family(commit)
    table_channel_real(commit)
    table_leakage(commit)
    table_traffic_detectability(commit)
    table_robustness(commit)
    table_comparative_robustness(commit)
    table_extended_robustness(commit)
    table_external_corpus(commit)
    table_stratified_robustness(commit)
    table_ecc_repetition(commit)
    print(
        "Note: tab_mapping_comparison and tab_codebook_geometry remain manually "
        "curated in paper/article_fham.tex (the former mixes structural, "
        "hand-derived nominal-capacity constants not stored in any CSV; the "
        "latter uses per-image display names not part of the raw data)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
