"""Apply G-T1/G-T2 and summarize the two Step 4b C3 reruns."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/stability_step1/step1ter/step4b_ceiling"
OUT = ROOT / "results/stability_step1/step1ter/step4b_summary"
Z = 1.959963984540054


def wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    den = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / den
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return max(0.0, center-half), min(1.0, center+half)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*_ceiling.csv"))
    if len(files) != 100:
        raise RuntimeError(f"Expected 100 completed D files, found {len(files)}")
    x = pd.concat([pd.read_csv(p) for p in files], ignore_index=True)
    if x.cover.nunique() != 100:
        raise RuntimeError("Expected 100 unique D covers")
    all12 = x.loc[x.attack.eq("feasibility_12_all") & x.source_length.eq(100)]
    g1_rows = []
    for (descriptor, bound), group in all12.groupby(["descriptor", "bound"], sort=True):
        k, n = int(group.feasible.sum()), len(group)
        low, high = wilson(k, n)
        point = k / n
        status = "green" if low >= .90 else "orange" if point >= .70 else "red"
        g1_rows.append({"descriptor": descriptor, "B": bound, "successes": k,
                        "covers": n, "point_estimate": point,
                        "wilson95_low": low, "wilson95_high": high, "G_T1": status})
    g1 = pd.DataFrame(g1_rows)
    g1.to_csv(OUT / "G_T1_by_descriptor_bound.csv", index=False)

    message = x.loc[~x.attack.isin(["feasibility_12_all", "none"])].copy()
    msum = message.groupby(["descriptor", "bound", "source_length", "family", "attack"], as_index=False).agg(
        successful_message_rows=("feasible", "size"), feasible_messages=("feasible", "sum"),
        mean_symbol_accuracy_when_feasible=("accuracy", "mean"),
        exact_compressed_messages=("exact_compressed", "sum"),
        exact_source_messages=("exact_source", "sum"),
        mean_fixed_bits=("fixed_bits_per_symbol", "mean"))
    msum.to_csv(OUT / "message_recovery_summary.csv", index=False)

    # Cluster bootstrap: one per-cover symbol accuracy, with infeasible messages
    # contributing zero. Conditional accuracy is also reported separately.
    rng = np.random.default_rng(20261118)
    draws = rng.integers(0, 100, size=(10000, 100))
    bycover = []
    for (descriptor, bound, source_length, attack), group in x.loc[
        x.attack.isin(["jpeg75", "noise2"])].groupby(
            ["descriptor", "bound", "source_length", "attack"], sort=True):
        for cover, cg in group.groupby("cover"):
            all_messages = x[(x.cover.eq(cover)) & x.descriptor.eq(descriptor)
                             & x.bound.eq(bound) & x.source_length.eq(source_length)]
            expected = int(all_messages.loc[~all_messages.attack.eq("feasibility_12_all"),
                                            ["family", "index", "compressed_length"]]
                           .drop_duplicates(["family", "index"]).compressed_length.sum())
            # One recovery row per feasible message and attack; unsuccessful
            # assignments have an attack='none' row and contribute zero bytes.
            feasible_bytes = int(cg.compressed_length.sum())
            correct = float((cg.accuracy * cg.compressed_length).sum())
            bycover.append({"cover": cover, "descriptor": descriptor, "bound": bound,
                            "source_length": source_length, "attack": attack,
                            "expected_bytes": expected, "feasible_bytes": feasible_bytes,
                            "correct_bytes": correct,
                            "accuracy_conditional": correct/feasible_bytes if feasible_bytes else np.nan,
                            "accuracy_unconditional": correct/expected if expected else 0.0})
    cover_acc = pd.DataFrame(bycover)
    cover_acc.to_csv(OUT / "per_cover_accuracy.csv", index=False)
    ci_rows = []
    for keys, group in cover_acc.groupby(["descriptor", "bound", "source_length", "attack"], sort=True):
        vals = group.set_index("cover").accuracy_unconditional.reindex(sorted(x.cover.unique())).fillna(0).to_numpy()
        boot = vals[draws].mean(axis=1)
        cond = group.accuracy_conditional.dropna().to_numpy()
        cond_draws = rng.integers(0, len(cond), size=(10000, len(cond))) if len(cond) else np.empty((0, 0))
        cond_boot = cond[cond_draws].mean(axis=1) if len(cond) else np.asarray([])
        ci_rows.append({"descriptor": keys[0], "B": keys[1], "source_length": keys[2],
                        "attack": keys[3], "covers": len(vals), "a_P3_unconditional": float(vals.mean()),
                        "unconditional_cluster95_low": float(np.quantile(boot, .025)),
                        "unconditional_cluster95_high": float(np.quantile(boot, .975)),
                        "a_P3_conditional": float(cond.mean()) if len(cond) else np.nan,
                        "conditional_cluster95_low": float(np.quantile(cond_boot, .025)) if len(cond) else np.nan,
                        "conditional_cluster95_high": float(np.quantile(cond_boot, .975)) if len(cond) else np.nan,
                        "mean_conditional_accuracy": float(group.accuracy_conditional.mean()),
                        "covers_with_feasible_case": int(group.feasible_bytes.gt(0).sum()),
                        "mean_exact_rate": float(x.loc[
                            x.descriptor.eq(keys[0]) & x.bound.eq(keys[1])
                            & x.source_length.eq(keys[2]) & x.attack.isin([keys[3], "none"])
                        ].exact_compressed.fillna(0).sum() / (100 * 12))})
    accuracy = pd.DataFrame(ci_rows)
    accuracy.to_csv(OUT / "G_T2_accuracy.csv", index=False)

    gate_rows = []
    for descriptor in sorted(x.descriptor.unique()):
        g1d = g1.loc[g1.descriptor.eq(descriptor)]
        candidate_rows = []
        for bound in (2, 4, 8):
            g1_green = bool(g1d.loc[g1d.B.eq(bound), "G_T1"].eq("green").any())
            acc_rows = accuracy.loc[(accuracy.descriptor.eq(descriptor))
                                    & accuracy.B.eq(bound) & accuracy.source_length.eq(100)]
            pass_attacks = all(
                ((acc_rows.loc[acc_rows.attack.eq(attack), "a_P3_conditional"] >= .95)
                 & (acc_rows.loc[acc_rows.attack.eq(attack), "conditional_cluster95_low"] >= .92)).all()
                and not acc_rows.loc[acc_rows.attack.eq(attack)].empty
                for attack in ("jpeg75", "noise2"))
            bits_ok = bool(x.loc[x.descriptor.eq(descriptor) & x.bound.eq(bound),
                                 "fixed_bits_per_symbol"].dropna().le(20).all())
            candidate_rows.append({"B": bound, "G_T1_green": g1_green,
                                   "G_T2_accuracy_ok": pass_attacks, "fixed_bits_le20": bits_ok,
                                   "passes_both": g1_green and pass_attacks and bits_ok})
        overall_g1 = any(r["G_T1_green"] for r in candidate_rows)
        overall_g2 = any(r["passes_both"] for r in candidate_rows)
        max_point = float(g1d.point_estimate.max())
        status = "green" if overall_g2 else "orange" if overall_g1 or max_point >= .70 else "red"
        gate_rows.append({"descriptor": descriptor, "G_T1_green_any_B": overall_g1,
                          "G_T2_accuracy_and_bits_same_B": overall_g2,
                          "by_B": json.dumps(candidate_rows), "G_T3": status})
    gate = pd.DataFrame(gate_rows)
    gate.to_csv(OUT / "G_T3.csv", index=False)
    overall = "green" if gate.G_T3.eq("green").any() else "orange" if gate.G_T3.eq("orange").any() else "red"
    decision = {"G_T3_overall": overall,
                "descriptor_decisions": gate.to_dict("records"),
                "E_C_F_evaluation_pixels_opened": False,
                "interpretation": "Exploratory D only. E remains reserved for Step 5 if a candidate is retained; C/F remain closed unless Step 6 is reached."}
    (OUT / "decision_G_T3.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
