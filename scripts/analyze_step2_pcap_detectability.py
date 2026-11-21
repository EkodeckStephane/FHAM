#!/usr/bin/env python3
"""Classify FHAM/control flows using features extracted from an actual loopback PCAPNG."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "results/step2/detection/full_capture"
OUT = ROOT / "results/step2/detection"
SEED = 20261121


def _parse_payload(value):
    result = []
    for field in str(value or "").split(","):
        raw = field.strip().replace(":", "")
        if len(raw) % 2:
            continue
        try:
            result.append(bytes.fromhex(raw))
        except ValueError:
            pass
    return result


def _extract(pcap: Path, tshark: str):
    command = [tshark, "-r", str(pcap), "-d", "tcp.port==45511,tls",
               "-Y", "tcp.port==45511", "-T", "fields",
               "-e", "tcp.stream", "-e", "tcp.srcport", "-e", "tcp.dstport",
               "-e", "frame.time_epoch", "-e", "frame.len", "-e", "tcp.len",
               "-e", "tls.record.length", "-e", "tls.record.content_type", "-e", "tcp.payload",
               "-E", "header=y", "-E", "separator=\t", "-E", "quote=d",
               "-E", "occurrence=a", "-E", "aggregator=,"]
    proc = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    from io import StringIO
    packets = pd.read_csv(StringIO(proc.stdout), sep="\t", keep_default_na=False, dtype=str)
    if packets.empty:
        raise RuntimeError("tshark found no TCP packets on the experiment port")
    packets.columns = ["stream", "srcport", "dstport", "time_epoch", "frame_len",
                       "tcp_len", "tls_record_length", "tls_content_type", "tcp_payload"]
    return packets


def _features(packets, manifest):
    map_port = {str(int(row.client_port)): row for row in manifest.itertuples(index=False)}
    flows = {}
    for packet in packets.itertuples(index=False):
        stream = str(packet.stream)
        src, dst = str(packet.srcport), str(packet.dstport)
        client_port = src if dst == "45511" else dst if src == "45511" else ""
        if client_port not in map_port:
            continue
        meta = map_port[client_port]
        item = flows.setdefault(stream, {"manifest": meta, "tx_frame": [], "rx_frame": [],
                                         "tx_tcp": [], "rx_tcp": [], "tx_tls": [], "rx_tls": [],
                                         "tx_types": [], "rx_types": [], "tx_marker": False})
        direction = "tx" if src == client_port else "rx"
        frame_len = int(packet.frame_len or 0)
        tcp_len = int(packet.tcp_len or 0)
        item[f"{direction}_frame"].append(frame_len)
        item[f"{direction}_tcp"].append(tcp_len)
        tls_lens = [int(x) for x in str(packet.tls_record_length or "").split(",") if x.isdigit()]
        tls_types = [int(x) for x in str(packet.tls_content_type or "").split(",") if x.isdigit()]
        item[f"{direction}_tls"].extend([x + 5 for x in tls_lens])
        item[f"{direction}_types"].extend(tls_types)
        if direction == "tx":
            item["tx_marker"] |= any(b"FHAM" in payload or b"FHQ2" in payload
                                     for payload in _parse_payload(packet.tcp_payload))
    rows = []
    for stream, item in flows.items():
        meta = item["manifest"]
        row = {"tcp_stream": stream, "condition": meta.condition, "transport": meta.transport,
               "mode": meta.mode, "split": meta.split, "label": meta.label,
               "base_session_id": meta.base_session_id,
               "tx_frame_bytes": sum(item["tx_frame"]), "rx_frame_bytes": sum(item["rx_frame"]),
               "tx_tcp_bytes": sum(item["tx_tcp"]), "rx_tcp_bytes": sum(item["rx_tcp"]),
               "tx_packets": len(item["tx_frame"]), "rx_packets": len(item["rx_frame"]),
               "tx_tls_count": len(item["tx_tls"]), "rx_tls_count": len(item["rx_tls"]),
               "tx_marker": int(item["tx_marker"])}
        for direction in ("tx", "rx"):
            frames, tls, types = item[f"{direction}_frame"], item[f"{direction}_tls"], item[f"{direction}_types"]
            row[f"{direction}_tls_ct22"] = sum(t == 22 for t in types)
            row[f"{direction}_tls_ct23"] = sum(t == 23 for t in types)
            for i in range(16):
                row[f"{direction}_frame_{i}"] = frames[i] if i < len(frames) else 0
                row[f"{direction}_tls_{i}"] = tls[i] if i < len(tls) else 0
        rows.append(row)
    return pd.DataFrame(rows)


def _models():
    return {"volume_only": None,
            "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=SEED)),
            "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                                       class_weight="balanced", random_state=SEED, n_jobs=1),
            "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=150, learning_rate=.08,
                                                                       max_leaf_nodes=15, l2_regularization=1.0,
                                                                       random_state=SEED)}


def _bootstrap_auc(y, score, groups, reps=10000):
    rng = np.random.default_rng(SEED)
    unique = np.unique(groups)
    out = np.empty(reps)
    for b in range(reps):
        sampled = rng.choice(unique, len(unique), replace=True)
        counts = pd.Series(sampled).value_counts().to_dict()
        weights = np.asarray([counts.get(g, 0) for g in groups], dtype=float)
        out[b] = roc_auc_score(y, score, sample_weight=weights)
    return tuple(float(x) for x in np.quantile(out, [.025, .975]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--tshark", default=shutil.which("tshark"))
    args = parser.parse_args()
    if not args.tshark:
        raise SystemExit("tshark not found; install Wireshark and rerun")
    pcap = args.pcap if args.pcap.is_absolute() else ROOT / args.pcap
    manifest = pd.read_csv(CAPTURE / "session_flow_manifest.csv", keep_default_na=False)
    acceptance = pd.read_csv(CAPTURE / "receiver_acceptance.csv", keep_default_na=False)
    if len(manifest) != 12800 or len(acceptance) != 12800:
        raise RuntimeError(f"full capture run is incomplete: flows={len(manifest)}, receiver_rows={len(acceptance)}")
    if not (acceptance.receiver_exact.astype(int) == 1).all():
        raise RuntimeError("one or more real receiver sessions failed exact recovery")
    packets = _extract(pcap, args.tshark)
    flows = _features(packets, manifest)
    if len(flows) != 12800 or set(flows.condition) != {"TCP_R0", "TCP_R1", "TLS13_R0", "TLS13_R1"}:
        raise RuntimeError(f"PCAP maps only {len(flows)} complete flows; expected 12,800")
    if not flows.groupby("condition").size().eq(3200).all():
        raise RuntimeError("PCAP flow counts do not match 3,200 sessions per condition")
    flows.to_csv(OUT / "pcap_detectability_flow_features.csv", index=False)
    results, prediction_rows = [], []
    for condition, frame in flows.groupby("condition", sort=True):
        frame = frame.reset_index(drop=True)
        y = (frame.label == "positive").astype(int).to_numpy()
        splits = frame.split.to_numpy()
        if frame.transport.iloc[0] == "TCP":
            used = ["tx_marker", "tx_frame_bytes", "rx_frame_bytes", "tx_tcp_bytes", "rx_tcp_bytes", "tx_packets", "rx_packets"]
            used += [f"{d}_frame_{i}" for d in ("tx", "rx") for i in range(16)]
        else:
            used = ["tx_frame_bytes", "rx_frame_bytes", "tx_tcp_bytes", "rx_tcp_bytes", "tx_packets", "rx_packets",
                    "tx_tls_count", "rx_tls_count", "tx_tls_ct22", "tx_tls_ct23", "rx_tls_ct22", "rx_tls_ct23"]
            used += [f"{d}_tls_{i}" for d in ("tx", "rx") for i in range(16)]
            used += [f"{d}_frame_{i}" for d in ("tx", "rx") for i in range(16)]
        x = frame[used].to_numpy(dtype=float)
        idx = {s: np.flatnonzero(splits == s) for s in ("train", "validation", "test")}
        candidates, fitted = _models(), {}
        val_auc = {}
        for name, model in candidates.items():
            if model is None:
                score = frame.tx_frame_bytes.to_numpy(dtype=float) + frame.rx_frame_bytes.to_numpy(dtype=float)
                train = idx["train"]
                if np.mean(score[train][y[train] == 1]) < np.mean(score[train][y[train] == 0]):
                    score = -score
            else:
                model.fit(x[idx["train"]], y[idx["train"]])
                score = model.predict_proba(x)[:, 1]
            val_auc[name] = float(roc_auc_score(y[idx["validation"]], score[idx["validation"]]))
            fitted[name] = score
        chosen = max(val_auc, key=val_auc.get)
        score = fitted[chosen]
        test = idx["test"]
        auc = float(roc_auc_score(y[test], score[test]))
        low, high = _bootstrap_auc(y[test], score[test], frame.base_session_id.to_numpy()[test])
        vfpr, vtpr, thresholds = roc_curve(y[idx["validation"]], score[idx["validation"]])
        threshold = float(thresholds[int(np.argmax(vtpr-vfpr))])
        fpr, tpr, _ = roc_curve(y[test], score[test])
        allowed = np.flatnonzero(fpr <= .01)
        results.append({"condition": condition, "flows": len(frame), "test_flows": len(test),
                        "selected_model": chosen, "validation_auc": val_auc[chosen], "test_auc": auc,
                        "test_auc_cluster_ci_low": low, "test_auc_cluster_ci_high": high,
                        "balanced_accuracy_at_validation_threshold": float(balanced_accuracy_score(y[test], score[test] >= threshold)),
                        "tpr_at_fpr_le_1pct": float(tpr[allowed[-1]]) if len(allowed) else 0.0,
                        "packet_features": ";".join(used), "validation_auc_by_model": json.dumps(val_auc, sort_keys=True)})
        pred = frame.iloc[test][["condition", "base_session_id", "label", "split"]].copy()
        pred["score"] = score[test]
        prediction_rows.append(pred)
    summary = pd.DataFrame(results)
    summary.to_csv(OUT / "pcap_detectability_summary.csv", index=False)
    pd.concat(prediction_rows, ignore_index=True).to_csv(OUT / "pcap_detectability_test_predictions.csv", index=False)
    import hashlib
    metadata = {"pcap": str(pcap), "pcap_sha256": hashlib.sha256(pcap.read_bytes()).hexdigest(),
                "tshark": args.tshark, "observed_packet_rows": int(len(packets)),
                "mapped_tcp_flows": int(len(flows)), "source_flow_manifest": str(CAPTURE / "session_flow_manifest.csv"),
                "feature_scope": "packet lengths/directions/TLS record lengths; no endpoint syscall features",
                "split": "pre-existing grouped train/validation/test; model chosen on validation, tested once",
                "bootstrap": "10,000 base-session-pair cluster resamples, seed 20261121"}
    (OUT / "pcap_detectability_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
