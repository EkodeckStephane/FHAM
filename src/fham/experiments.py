import csv
import os
import random
import time
import tracemalloc
import zlib
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
from scipy import stats as scipy_stats
from scipy.ndimage import gaussian_filter, median_filter
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    mutual_info_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from .abdulsattar import AbdulsattarMethod
from .assignment import (
    aggregated_min_cost_assignment,
    bottleneck_radius,
    codebook_counts,
    dense_min_cost,
    symbol_counts,
)
from .channel import AuxiliaryChannel
from .config import DATASET_DIR, MESSAGE_LENGTHS, PRINTABLE_ASCII, RANDOM_SEED, ROOT
from .descriptors import descriptor_hashes
from .ecc import repetition_decode, repetition_encode
from .methods import (
    Assignment,
    BottleneckAssignmentMethod,
    BoundedAssignmentMethod,
    ExactMatchMethod,
    GreedyAssignmentMethod,
    OptimalAssignmentMethod,
    RandomFeasibleAssignmentMethod,
    StabilityAwareAssignmentMethod,
)
from .wysawis import WysawisMethod


def _message(length, image_name, trial):
    seed = RANDOM_SEED + length * 1009 + trial * 97
    seed += zlib.crc32(image_name.encode("utf-8"))
    rng = random.Random(seed)
    return "".join(chr(rng.choice(PRINTABLE_ASCII)) for _ in range(length))


def capacity_experiment(images, trials=10):
    rows = []
    for image_name, image in images.items():
        baseline = ExactMatchMethod()
        baseline.build_lookup_table(image)
        optimal = BoundedAssignmentMethod(2)
        optimal.lookup_table = baseline.lookup_table
        optimal.image_shape = baseline.image_shape
        for length in MESSAGE_LENGTHS:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                baseline_assignment = baseline.embed(message, image)
                optimal_assignment = optimal.embed(message, image)
                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "baseline_success": int(baseline_assignment is not None),
                        "fham_success": int(optimal_assignment is not None),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        baseline_success=("baseline_success", "mean"),
        fham_success=("fham_success", "mean"),
    )
    return summary, raw


def stress_capacity_experiment(images, lengths=(100, 200), trials=3):
    summary, raw = capacity_experiment_subset(images, lengths, trials)
    return summary, raw


def capacity_experiment_subset(images, lengths, trials):
    rows = []
    for image_name, image in images.items():
        baseline = ExactMatchMethod()
        baseline.build_lookup_table(image)
        optimal = OptimalAssignmentMethod()
        optimal.lookup_table = baseline.lookup_table
        optimal.image_shape = baseline.image_shape
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "baseline_success": int(
                            baseline.embed(message, image) is not None
                        ),
                        "fham_success": int(optimal.embed(message, image) is not None),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        trials=("fham_success", "size"),
        baseline_success=("baseline_success", "mean"),
        fham_success=("fham_success", "mean"),
    )
    return summary, raw


def assignment_ablation(images, lengths=(20, 50, 100, 200), trials=10):
    rows = []
    for image_name, image in images.items():
        greedy = GreedyAssignmentMethod()
        greedy.build_lookup_table(image)
        optimal = OptimalAssignmentMethod()
        optimal.lookup_table = greedy.lookup_table
        optimal.image_shape = greedy.image_shape
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                start = time.perf_counter()
                greedy_assignment = greedy.embed(message, image)
                greedy_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                optimal_assignment = optimal.embed(message, image)
                optimal_ms = (time.perf_counter() - start) * 1000
                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "greedy_displacement": sum(
                            map(abs, greedy_assignment.displacements)
                        ),
                        "optimal_displacement": sum(
                            map(abs, optimal_assignment.displacements)
                        ),
                        "greedy_ms": greedy_ms,
                        "optimal_ms": optimal_ms,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        greedy_displacement=("greedy_displacement", "mean"),
        optimal_displacement=("optimal_displacement", "mean"),
        greedy_ms=("greedy_ms", "mean"),
        optimal_ms=("optimal_ms", "mean"),
    )
    return summary, raw


def codebook_geometry(images):
    rows = []
    for image_name, image in images.items():
        method = OptimalAssignmentMethod()
        method.build_lookup_table(image)
        values = sorted(method.lookup_table)
        radius = max(
            min(abs(target - value) for value in values) for target in range(256)
        )
        rows.append(
            {
                "image": image_name,
                "locations": method.capacity,
                "distinct_hashes": len(values),
                "density": len(values) / 256,
                "covering_radius": radius,
            }
        )
    return pd.DataFrame(rows)


def bounded_assignment_experiment(
    images, bounds=(0, 1, 2, 4, 8, 16, 32, 64, 128, 255), lengths=(50, 100, 200), trials=5
):
    rows = []
    for image_name, image in images.items():
        lookup = OptimalAssignmentMethod()
        lookup.build_lookup_table(image)
        for bound in bounds:
            method = BoundedAssignmentMethod(bound)
            method.lookup_table = lookup.lookup_table
            method.image_shape = lookup.image_shape
            for length in lengths:
                for trial in range(trials):
                    message = _message(length, image_name, trial)
                    assignment = method.embed(message, image)
                    rows.append(
                        {
                            "image": image_name,
                            "bound": bound,
                            "length": length,
                            "trial": trial,
                            "success": int(assignment is not None),
                            "displacement": (
                                sum(map(abs, assignment.displacements))
                                if assignment is not None
                                else np.nan
                            ),
                        }
                    )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["bound", "length"], as_index=False).agg(
        success=("success", "mean"),
        mean_displacement=("displacement", "mean"),
    )
    return summary, raw


def _attack(image, name, seed):
    source = Image.fromarray(image)
    if name == "jpeg90" or name == "jpeg75":
        buffer = BytesIO()
        source.save(buffer, format="JPEG", quality=int(name[-2:]))
        buffer.seek(0)
        return np.asarray(Image.open(buffer).convert("L"))
    if name == "resize90":
        reduced = source.resize((461, 461), Image.Resampling.LANCZOS)
        return np.asarray(reduced.resize((512, 512), Image.Resampling.LANCZOS))
    if name == "rotate1":
        return np.asarray(
            source.rotate(1, resample=Image.Resampling.BILINEAR, fillcolor=0)
        )
    rng = np.random.default_rng(seed)
    sigma = 1 if name == "noise1" else 2
    return np.clip(image.astype(np.float64) + rng.normal(0, sigma, image.shape), 0, 255).astype(np.uint8)


def _wysawis_attack(image, name, seed):
    if name == "identity":
        return image
    rng = np.random.default_rng(seed)
    source = image.astype(np.float64)
    if name == "speckle005":
        noise = rng.normal(0, np.sqrt(0.005), image.shape)
        return np.clip(source + source * noise, 0, 255).astype(np.uint8)
    if name == "saltpepper005":
        attacked = image.copy()
        count = int(image.size * 0.005 / 2)
        indices = rng.choice(image.size, 2 * count, replace=False)
        attacked.flat[indices[:count]] = 0
        attacked.flat[indices[count:]] = 255
        return attacked
    if name == "gaussian_filter5":
        return np.clip(
            gaussian_filter(source, sigma=1, radius=2), 0, 255
        ).astype(np.uint8)
    if name == "median_filter5":
        return median_filter(image, size=5).astype(np.uint8)
    raise ValueError(f"unknown WYSAWIS comparison attack: {name}")


def robustness_experiment(
    images,
    attacks=("identity", "jpeg90", "jpeg75", "resize90", "rotate1", "noise1", "noise2"),
    length=100,
    trials=5,
):
    rows = []
    for image_name, image in images.items():
        method = OptimalAssignmentMethod()
        method.build_lookup_table(image)
        for trial in range(trials):
            message = _message(length, image_name, trial)
            assignment = method.embed(message, image)
            for attack_name in attacks:
                attacked = (
                    image
                    if attack_name == "identity"
                    else _attack(
                        image,
                        attack_name,
                        RANDOM_SEED + trial + zlib.crc32(image_name.encode()),
                    )
                )
                recovered = method.extract(assignment, attacked)
                correct = sum(a == b for a, b in zip(message, recovered))
                rows.append(
                    {
                        "image": image_name,
                        "trial": trial,
                        "attack": attack_name,
                        "exact_recovery": int(recovered == message),
                        "character_accuracy": correct / length,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("attack", as_index=False).agg(
        exact_recovery=("exact_recovery", "mean"),
        character_accuracy=("character_accuracy", "mean"),
        character_accuracy_std=("character_accuracy", "std"),
    )
    return summary, raw


def comparative_mapping_experiment(
    images, lengths=(50, 100, 200), trials=5
):
    rows = []
    for image_name, image in images.items():
        wysawis = WysawisMethod()
        adequate = wysawis.build_index(image)
        fham = BoundedAssignmentMethod(2)
        fham.build_lookup_table(image)
        abdulsattar = AbdulsattarMethod(overlapping=True)
        abdulsattar.build_lookup_table(image)
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                fham_assignment = fham.embed(message, image)
                wysawis_assignment = wysawis.embed(message, image)
                abdulsattar_assignment = abdulsattar.embed(message, image)
                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "wysawis_adequate": int(adequate),
                        "fham_success": int(fham_assignment is not None),
                        "wysawis_success": int(wysawis_assignment is not None),
                        "abdulsattar_success": int(
                            abdulsattar_assignment is not None
                        ),
                        "fham_records": (
                            len(fham_assignment.locations)
                            if fham_assignment is not None
                            else np.nan
                        ),
                        "wysawis_cloud_records": (
                            WysawisMethod.cloud_records(wysawis_assignment)
                            if wysawis_assignment is not None
                            else np.nan
                        ),
                        "abdulsattar_records": (
                            len(abdulsattar_assignment.locations)
                            if abdulsattar_assignment is not None
                            else np.nan
                        ),
                        "wysawis_location_lower_bound_bits": (
                            WysawisMethod.location_information_lower_bound(
                                wysawis_assignment
                            )
                            if wysawis_assignment is not None
                            else np.nan
                        ),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        images=("image", "nunique"),
        wysawis_adequacy=("wysawis_adequate", "mean"),
        fham_success=("fham_success", "mean"),
        wysawis_success=("wysawis_success", "mean"),
        abdulsattar_success=("abdulsattar_success", "mean"),
        fham_records=("fham_records", "mean"),
        wysawis_cloud_records=("wysawis_cloud_records", "mean"),
        abdulsattar_records=("abdulsattar_records", "mean"),
        wysawis_location_lower_bound_bits=(
            "wysawis_location_lower_bound_bits",
            "mean",
        ),
    )
    return summary, raw


def comparative_robustness_experiment(
    images,
    attacks=(
        "identity",
        "speckle005",
        "saltpepper005",
        "gaussian_filter5",
        "median_filter5",
    ),
    length=50,
    trials=5,
):
    rows = []
    for image_name, image in images.items():
        fham = BoundedAssignmentMethod(2)
        fham.build_lookup_table(image)
        wysawis = WysawisMethod()
        if not wysawis.build_index(image):
            continue
        abdulsattar = AbdulsattarMethod(overlapping=True)
        abdulsattar.build_lookup_table(image)
        for trial in range(trials):
            message = _message(length, image_name, trial)
            expected = message.encode("utf-8")
            expected_bits = [
                (byte >> shift) & 1
                for byte in expected
                for shift in range(7, -1, -1)
            ]
            fham_assignment = fham.embed(message, image)
            wysawis_assignment = wysawis.embed(message, image)
            abdulsattar_assignment = abdulsattar.embed(message, image)
            if (
                fham_assignment is None
                or wysawis_assignment is None
                or abdulsattar_assignment is None
            ):
                continue
            for attack_name in attacks:
                attacked = _wysawis_attack(
                    image,
                    attack_name,
                    RANDOM_SEED + trial + zlib.crc32(image_name.encode()),
                )
                recovered = fham.extract(fham_assignment, attacked)
                recovered_bits = [
                    (byte >> shift) & 1
                    for byte in recovered.encode("latin-1")
                    for shift in range(7, -1, -1)
                ]
                correct = sum(
                    left == right
                    for left, right in zip(expected_bits, recovered_bits)
                )
                rows.append(
                    {
                        "image": image_name,
                        "trial": trial,
                        "method": "FHAM B=2",
                        "attack": attack_name,
                        "exact_recovery": int(recovered == message),
                        "extraction_rate": 1.0,
                        "bit_accuracy": correct / len(expected_bits),
                    }
                )

                recovered_bits, valid = wysawis.extract_bits(
                    wysawis_assignment, attacked
                )
                correct = sum(
                    is_valid and left == right
                    for left, right, is_valid in zip(
                        expected_bits, recovered_bits, valid
                    )
                )
                rows.append(
                    {
                        "image": image_name,
                        "trial": trial,
                        "method": "WYSAWIS core",
                        "attack": attack_name,
                        "exact_recovery": int(
                            all(valid) and recovered_bits == expected_bits
                        ),
                        "extraction_rate": sum(valid) / len(valid),
                        "bit_accuracy": correct / len(expected_bits),
                    }
                )

                recovered = abdulsattar.extract(abdulsattar_assignment, attacked)
                recovered_bits = [
                    (byte >> shift) & 1
                    for byte in recovered.encode("latin-1")
                    for shift in range(7, -1, -1)
                ]
                correct = sum(
                    left == right
                    for left, right in zip(expected_bits, recovered_bits)
                )
                rows.append(
                    {
                        "image": image_name,
                        "trial": trial,
                        "method": "Abdulsattar Arr.4",
                        "attack": attack_name,
                        "exact_recovery": int(recovered == message),
                        "extraction_rate": 1.0,
                        "bit_accuracy": correct / len(expected_bits),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["method", "attack"], as_index=False).agg(
        trials=("exact_recovery", "size"),
        exact_recovery=("exact_recovery", "mean"),
        extraction_rate=("extraction_rate", "mean"),
        bit_accuracy=("bit_accuracy", "mean"),
        bit_accuracy_std=("bit_accuracy", "std"),
    )
    return summary, raw


def channel_experiment(images, lengths=(10, 20, 50, 100, 200), trials=10):
    key = os.urandom(32)
    shaped_record_capacity = max(lengths)
    rows = []
    for image_name, image in images.items():
        method = OptimalAssignmentMethod()
        method.build_lookup_table(image)
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                assignment = method.embed(message, image)
                raw_payload = AuxiliaryChannel.serialize(assignment)
                compressed = zlib.compress(raw_payload, level=9)
                direct_compressed = zlib.compress(message.encode("ascii"), level=9)
                direct_nonce = os.urandom(12)
                direct_ciphertext = AESGCM(key).encrypt(
                    direct_nonce, direct_compressed, b"FHAM-DIRECT-BASELINE"
                )
                direct_bytes = 13 + len(direct_nonce) + len(direct_ciphertext)

                tracemalloc.start()
                start = time.perf_counter()
                envelope = AuxiliaryChannel.protect(assignment, key)
                encrypt_ms = (time.perf_counter() - start) * 1000
                _, encrypt_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                tracemalloc.start()
                start = time.perf_counter()
                shaped_envelope = AuxiliaryChannel.protect_shaped(
                    assignment, key, shaped_record_capacity
                )
                shaped_encrypt_ms = (time.perf_counter() - start) * 1000
                _, shaped_encrypt_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                tracemalloc.start()
                start = time.perf_counter()
                recovered = AuxiliaryChannel.recover(envelope, key)
                decrypt_ms = (time.perf_counter() - start) * 1000
                _, decrypt_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                tracemalloc.start()
                start = time.perf_counter()
                shaped_recovered = AuxiliaryChannel.recover_shaped(shaped_envelope, key)
                shaped_decrypt_ms = (time.perf_counter() - start) * 1000
                _, shaped_decrypt_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                if recovered != assignment:
                    raise RuntimeError("auxiliary channel round trip failed")
                if shaped_recovered != assignment:
                    raise RuntimeError("shaped auxiliary channel round trip failed")

                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "message_bytes": length,
                        "raw_bytes": len(raw_payload),
                        "compressed_bytes": len(compressed),
                        "encrypted_bytes": len(envelope),
                        "direct_encrypted_bytes": direct_bytes,
                        "fham_to_direct_ratio": len(envelope) / direct_bytes,
                        "shaped_record_capacity": shaped_record_capacity,
                        "shaped_encrypted_bytes": len(shaped_envelope),
                        "shaped_to_direct_ratio": len(shaped_envelope) / direct_bytes,
                        "shaped_to_compact_ratio": len(shaped_envelope) / len(envelope),
                        "encrypted_to_message_ratio": len(envelope) / length,
                        "shaped_to_message_ratio": len(shaped_envelope) / length,
                        "encrypted_to_cover_ratio": len(envelope) / image.nbytes,
                        "shaped_to_cover_ratio": len(shaped_envelope) / image.nbytes,
                        "encrypt_ms": encrypt_ms,
                        "decrypt_ms": decrypt_ms,
                        "shaped_encrypt_ms": shaped_encrypt_ms,
                        "shaped_decrypt_ms": shaped_decrypt_ms,
                        "encrypt_peak_kib": encrypt_peak / 1024,
                        "decrypt_peak_kib": decrypt_peak / 1024,
                        "shaped_encrypt_peak_kib": shaped_encrypt_peak / 1024,
                        "shaped_decrypt_peak_kib": shaped_decrypt_peak / 1024,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        raw_bytes=("raw_bytes", "mean"),
        compressed_bytes=("compressed_bytes", "mean"),
        encrypted_bytes=("encrypted_bytes", "mean"),
        direct_encrypted_bytes=("direct_encrypted_bytes", "mean"),
        fham_to_direct_ratio=("fham_to_direct_ratio", "mean"),
        shaped_record_capacity=("shaped_record_capacity", "first"),
        shaped_encrypted_bytes=("shaped_encrypted_bytes", "mean"),
        shaped_to_direct_ratio=("shaped_to_direct_ratio", "mean"),
        shaped_to_compact_ratio=("shaped_to_compact_ratio", "mean"),
        encrypted_to_message_ratio=("encrypted_to_message_ratio", "mean"),
        shaped_to_message_ratio=("shaped_to_message_ratio", "mean"),
        encrypted_to_cover_ratio=("encrypted_to_cover_ratio", "mean"),
        shaped_to_cover_ratio=("shaped_to_cover_ratio", "mean"),
        encrypt_ms=("encrypt_ms", "mean"),
        decrypt_ms=("decrypt_ms", "mean"),
        shaped_encrypt_ms=("shaped_encrypt_ms", "mean"),
        shaped_decrypt_ms=("shaped_decrypt_ms", "mean"),
        encrypt_peak_kib=("encrypt_peak_kib", "mean"),
        decrypt_peak_kib=("decrypt_peak_kib", "mean"),
        shaped_encrypt_peak_kib=("shaped_encrypt_peak_kib", "mean"),
        shaped_decrypt_peak_kib=("shaped_decrypt_peak_kib", "mean"),
    )
    return summary, raw


def descriptor_comparison_experiment(
    images,
    descriptors=("spectral", "dct_ordinal", "wavelet_gradient"),
    lengths=(50, 100, 200),
    trials=10,
    bound=2,
):
    """Exercises the three implemented descriptor families (D0 spectral, D1
    DCT ordinal, D2 wavelet-gradient) under the identical bounded-assignment
    protocol, reporting unfavorable results alongside favorable ones rather
    than silently keeping only the spectral descriptor used elsewhere."""
    rows = []
    for image_name, image in images.items():
        for descriptor in descriptors:
            method = BoundedAssignmentMethod(bound, descriptor=descriptor)
            build_start = time.perf_counter()
            method.build_lookup_table(image)
            build_ms = (time.perf_counter() - build_start) * 1000
            capacity = method.capacity
            distinct_hashes = len(method.lookup_table)
            hashes = [
                value
                for value, locations in method.lookup_table.items()
                for _ in locations
            ]
            for length in lengths:
                for trial in range(trials):
                    message = _message(length, image_name, trial)
                    start = time.perf_counter()
                    assignment = method.embed(message, image)
                    embed_ms = (time.perf_counter() - start) * 1000
                    # B* requires an O(log 256) binary search over min-cost-flow
                    # feasibility checks; computed once per (image, descriptor,
                    # length) on trial 0 rather than every trial to keep the
                    # full sweep tractable.
                    b_star = (
                        bottleneck_radius(symbol_counts(message), codebook_counts(hashes))
                        if trial == 0
                        else np.nan
                    )
                    rows.append(
                        {
                            "image": image_name,
                            "descriptor": descriptor,
                            "length": length,
                            "trial": trial,
                            "capacity": capacity,
                            "distinct_hashes": distinct_hashes,
                            "build_ms": build_ms,
                            "success": int(assignment is not None),
                            "displacement": (
                                sum(map(abs, assignment.displacements))
                                if assignment is not None
                                else np.nan
                            ),
                            "embed_ms": embed_ms,
                            "b_star": b_star,
                        }
                    )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["descriptor", "length"], as_index=False).agg(
        capacity=("capacity", "mean"),
        distinct_hashes=("distinct_hashes", "mean"),
        mean_build_ms=("build_ms", "mean"),
        success=("success", "mean"),
        mean_displacement=("displacement", "mean"),
        mean_embed_ms=("embed_ms", "mean"),
        b_star_median=("b_star", "median"),
    )
    return summary, raw


def formulation_comparison_experiment(
    images, lengths=(50, 100, 200, 400), trials=5, bound=2
):
    """Empirically compares the dense symbol-position matrix formulation
    (`dense_min_cost`) against the aggregated 256-value min-cost-flow
    formulation (`aggregated_min_cost_assignment`) on identical codebooks and
    messages, checking cost equivalence and comparing running time."""
    rows = []
    for image_name, image in images.items():
        method = OptimalAssignmentMethod()
        method.build_lookup_table(image)
        hashes = [
            value
            for value, locations in method.lookup_table.items()
            for _ in locations
        ]
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                targets = [ord(character) for character in message]
                if len(targets) > len(hashes):
                    continue
                start = time.perf_counter()
                dense_cost = dense_min_cost(targets, hashes, bound)
                dense_ms = (time.perf_counter() - start) * 1000

                start = time.perf_counter()
                aggregated = aggregated_min_cost_assignment(
                    symbol_counts(message), codebook_counts(hashes), bound
                )
                aggregated_ms = (time.perf_counter() - start) * 1000
                aggregated_cost = aggregated.cost if aggregated.feasible else None

                rows.append(
                    {
                        "image": image_name,
                        "length": length,
                        "trial": trial,
                        "dense_feasible": int(dense_cost is not None),
                        "aggregated_feasible": int(aggregated.feasible),
                        "dense_cost": dense_cost,
                        "aggregated_cost": aggregated_cost,
                        "costs_match": (
                            int(dense_cost == aggregated_cost)
                            if dense_cost is not None and aggregated_cost is not None
                            else np.nan
                        ),
                        "dense_ms": dense_ms,
                        "aggregated_ms": aggregated_ms,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("length", as_index=False).agg(
        trials=("dense_feasible", "size"),
        dense_feasible=("dense_feasible", "mean"),
        aggregated_feasible=("aggregated_feasible", "mean"),
        cost_agreement=("costs_match", "mean"),
        mean_dense_ms=("dense_ms", "mean"),
        mean_aggregated_ms=("aggregated_ms", "mean"),
    )
    return summary, raw


def assignment_method_comparison_experiment(
    images,
    bound=2,
    lengths=(50, 100, 200),
    trials=10,
    seed=RANDOM_SEED,
    stability_aware_lambda=0.75,
    stability_dev_attacks=("jpeg90", "resize90", "noise1"),
):
    """Ablation A1-A6 (exact matching, greedy, global L1, bottleneck,
    random-feasible, stability-aware) on the identical spectral codebook,
    reporting success, total and maximum displacement, and running time for
    each method. The stability-aware method uses the lambda selected and
    frozen by ``stability_aware_lambda_sweep_experiment``."""
    rows = []
    for image_name, image in images.items():
        lookup = OptimalAssignmentMethod()
        lookup.build_lookup_table(image)
        stability_aware = StabilityAwareAssignmentMethod(
            bound, stability_aware_lambda
        )
        stability_aware.stabilities = _location_stabilities(
            lookup, image, stability_dev_attacks, image_name
        )
        methods = {
            "exact_matching": ExactMatchMethod(),
            "greedy": GreedyAssignmentMethod(),
            "global_l1": BoundedAssignmentMethod(bound),
            "bottleneck": BottleneckAssignmentMethod(bound),
            "random_feasible": RandomFeasibleAssignmentMethod(bound, seed=seed),
            "stability_aware": stability_aware,
        }
        for method in methods.values():
            method.lookup_table = lookup.lookup_table
            method.image_shape = lookup.image_shape
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                for method_name, method in methods.items():
                    start = time.perf_counter()
                    assignment = method.embed(message, image)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    displacements = (
                        assignment.displacements if assignment is not None else []
                    )
                    rows.append(
                        {
                            "image": image_name,
                            "method": method_name,
                            "length": length,
                            "trial": trial,
                            "success": int(assignment is not None),
                            "total_displacement": (
                                sum(map(abs, displacements))
                                if assignment is not None
                                else np.nan
                            ),
                            "max_displacement": (
                                max(map(abs, displacements))
                                if assignment is not None and displacements
                                else np.nan
                            ),
                            "time_ms": elapsed_ms,
                        }
                    )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["method", "length"], as_index=False).agg(
        success=("success", "mean"),
        mean_total_displacement=("total_displacement", "mean"),
        mean_max_displacement=("max_displacement", "mean"),
        mean_time_ms=("time_ms", "mean"),
    )
    return summary, raw


def _location_stabilities(lookup, image, attacks, image_name):
    identity_hashes = {
        location: value
        for value, locations in lookup.lookup_table.items()
        for location in locations
    }
    counters = {location: 0 for location in identity_hashes}
    for attack_index, attack_name in enumerate(attacks):
        attacked = _attack(
            image,
            attack_name,
            RANDOM_SEED + attack_index + zlib.crc32(image_name.encode()),
        )
        for location, expected_value in identity_hashes.items():
            block = attacked[
                location.y : location.y + lookup.block_size,
                location.x : location.x + lookup.block_size,
            ]
            value = descriptor_hashes(block, lookup.descriptor)[location.arrangement]
            if value == expected_value:
                counters[location] += 1
    return {
        location: counters[location] / len(attacks) for location in identity_hashes
    }


def stability_aware_lambda_sweep_experiment(
    images,
    dev_attacks=("jpeg90", "resize90", "noise1"),
    holdout_attacks=("jpeg75", "rotate1", "noise2"),
    lambdas=(0.0, 0.25, 0.5, 0.75, 1.0),
    length=100,
    trials=5,
    bound=8,
):
    """Sweeps lambda for the composite stability-aware cost
    c = lambda * normalized_residual + (1 - lambda) * (1 - stability).
    Per-location stability is estimated on a development subset of the
    transformation channel and recovery is measured on a disjoint validation
    subset, so the reported validation numbers are not circular with the
    stability estimate itself. The parameter name ``holdout_attacks`` and
    archived ``holdout_*`` columns are retained for backward compatibility;
    this subset is used for lambda selection and is therefore not an
    independent final test set. All lambda values are reported, including
    unfavorable ones."""
    rows = []
    for image_name, image in images.items():
        lookup = OptimalAssignmentMethod()
        lookup.build_lookup_table(image)
        stabilities = _location_stabilities(lookup, image, dev_attacks, image_name)
        for lam in lambdas:
            method = StabilityAwareAssignmentMethod(bound, lam)
            method.lookup_table = lookup.lookup_table
            method.image_shape = lookup.image_shape
            method.stabilities = stabilities
            for trial in range(trials):
                message = _message(length, image_name, trial)
                assignment = method.embed(message, image)
                success = assignment is not None
                exact_hits = []
                accuracies = []
                if success:
                    for attack_index, attack_name in enumerate(holdout_attacks):
                        attacked = _attack(
                            image,
                            attack_name,
                            RANDOM_SEED
                            + 1000
                            + attack_index
                            + trial
                            + zlib.crc32(image_name.encode()),
                        )
                        recovered = method.extract(assignment, attacked)
                        exact_hits.append(int(recovered == message))
                        accuracies.append(
                            sum(a == b for a, b in zip(message, recovered)) / length
                        )
                rows.append(
                    {
                        "image": image_name,
                        "lambda": lam,
                        "trial": trial,
                        "success": int(success),
                        "total_displacement": (
                            sum(map(abs, assignment.displacements))
                            if success
                            else np.nan
                        ),
                        "holdout_exact_recovery": (
                            float(np.mean(exact_hits)) if exact_hits else np.nan
                        ),
                        "holdout_character_accuracy": (
                            float(np.mean(accuracies)) if accuracies else np.nan
                        ),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("lambda", as_index=False).agg(
        success=("success", "mean"),
        mean_total_displacement=("total_displacement", "mean"),
        holdout_exact_recovery=("holdout_exact_recovery", "mean"),
        holdout_character_accuracy=("holdout_character_accuracy", "mean"),
    )
    return summary, raw


def _load_manifest_messages():
    path = DATASET_DIR / "message_manifests" / "message_seeds.csv"
    messages = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["family"], int(row["length_bytes"]))
            file_path = Path(row["path"])
            if not file_path.is_absolute():
                file_path = ROOT / file_path
            messages.setdefault(key, []).append(
                (row["message_id"], file_path.read_bytes())
            )
    return messages


def message_family_experiment(images, bound=2):
    """Exercises the full deterministic message manifest generated by
    scripts/generate_messages.py: 4 families (uniform_bytes, printable_ascii,
    natural_text, adversarial_repeated) at 8 byte lengths from 10 to 1600,
    instead of the single ad hoc printable-ASCII generator used by the other
    experiments in this module."""
    manifest = _load_manifest_messages()
    rows = []
    for image_name, image in images.items():
        method = BoundedAssignmentMethod(bound)
        method.build_lookup_table(image)
        for (family, length), entries in manifest.items():
            for message_id, payload in entries:
                text = payload.decode("latin-1")
                assignment = method.embed(text, image)
                rows.append(
                    {
                        "image": image_name,
                        "family": family,
                        "length": length,
                        "message_id": message_id,
                        "success": int(assignment is not None),
                        "displacement": (
                            sum(map(abs, assignment.displacements))
                            if assignment is not None
                            else np.nan
                        ),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["family", "length"], as_index=False).agg(
        trials=("success", "size"),
        success=("success", "mean"),
        mean_displacement=("displacement", "mean"),
    )
    return summary, raw


def leakage_experiment(
    images, lengths=(10, 20, 50, 100, 200), trials=10, size_class_bytes=64, bound=2
):
    """Measures message-length leakage through the protected-envelope size,
    before and after padding to fixed-width size classes. Reports the Pearson
    correlation and the mutual information (in bits) between message length
    and observable envelope size, both raw and padded, rather than treating
    the AES-GCM ciphertext-indistinguishability guarantee as covering length
    observability."""
    key = os.urandom(32)
    shaped_record_capacity = max(lengths)
    rows = []
    for image_name, image in images.items():
        method = BoundedAssignmentMethod(bound)
        method.build_lookup_table(image)
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                assignment = method.embed(message, image)
                if assignment is None:
                    continue
                envelopes = {
                    "compact": AuxiliaryChannel.protect(assignment, key),
                    "shaped": AuxiliaryChannel.protect_shaped(
                        assignment, key, shaped_record_capacity
                    ),
                }
                for envelope_mode, envelope in envelopes.items():
                    raw_size = len(envelope)
                    size_class = -(-raw_size // size_class_bytes)
                    padded_size = size_class * size_class_bytes
                    rows.append(
                        {
                            "envelope_mode": envelope_mode,
                            "image": image_name,
                            "length": length,
                            "trial": trial,
                            "record_capacity": (
                                shaped_record_capacity
                                if envelope_mode == "shaped"
                                else len(assignment.locations)
                            ),
                            "raw_size": raw_size,
                            "padded_size": padded_size,
                            "size_class": size_class,
                        }
                    )
    raw = pd.DataFrame(rows)
    bits_per_nat = 1.0 / np.log(2.0)

    def safe_pearson(x, y):
        if len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
            return 0.0
        return float(scipy_stats.pearsonr(x, y)[0])

    summary_rows = []
    for envelope_mode, group in raw.groupby("envelope_mode", sort=False):
        lengths_arr = group["length"].to_numpy()
        pearson_raw = safe_pearson(lengths_arr, group["raw_size"].to_numpy())
        pearson_padded = safe_pearson(lengths_arr, group["padded_size"].to_numpy())
        mi_raw_bits = (
            mutual_info_score(lengths_arr, group["raw_size"].to_numpy()) * bits_per_nat
        )
        mi_class_bits = (
            mutual_info_score(lengths_arr, group["size_class"].to_numpy()) * bits_per_nat
        )
        summary_rows.append(
            {
                "envelope_mode": envelope_mode,
                "size_class_bytes": size_class_bytes,
                "trials": len(group),
                "record_capacity": int(group["record_capacity"].max()),
                "distinct_lengths": int(group["length"].nunique()),
                "distinct_raw_sizes": int(group["raw_size"].nunique()),
                "distinct_size_classes": int(group["size_class"].nunique()),
                "pearson_length_vs_raw_size": pearson_raw,
                "pearson_length_vs_padded_size": pearson_padded,
                "mutual_info_length_vs_raw_size_bits": mi_raw_bits,
                "mutual_info_length_vs_size_class_bits": mi_class_bits,
            }
        )
    summary = pd.DataFrame(summary_rows)
    return summary, raw


def causal_codebook_ablation_experiment(
    images,
    length=200,
    trials=10,
    bound=2,
    stability_aware_lambda=0.75,
    stability_dev_attacks=("jpeg90", "resize90", "noise1"),
):
    """Crosses four codebooks (D0 spectral, D1 DCT-ordinal, D2
    wavelet-gradient, and Abdulsattar's Arr.4 codebook) with the same set of
    assignment strategies (exact matching, bounded global L1 at ``bound``,
    unbounded global L1, and stability-aware where a compatible stability
    estimate exists) on identical images and messages, so that any gain can be
    attributed to the assignment rule rather than to a simultaneous change of
    descriptor. Abdulsattar's published protocol performs exact matching, so
    its "exact_matching" row already represents its original protocol; FHAM's
    bounded/global solvers only require a value-to-locations lookup table and
    are applied directly to Abdulsattar's codebook without altering it.
    Stability-aware assignment requires re-hashing a location with the same
    descriptor used to build the codebook and is therefore reported only for
    the three FHAM descriptors, not for Abdulsattar's incompatible hash
    function; that cell is left absent rather than filled with a fabricated
    number."""
    rows = []
    for image_name, image in images.items():
        fham_lookups = {}
        for descriptor in ("spectral", "dct_ordinal", "wavelet_gradient"):
            lookup = OptimalAssignmentMethod(descriptor=descriptor)
            lookup.build_lookup_table(image)
            fham_lookups[descriptor] = lookup

        abdulsattar = AbdulsattarMethod(overlapping=True)
        abdulsattar.build_lookup_table(image)

        codebooks = list(fham_lookups.items()) + [("abdulsattar_arr4", abdulsattar)]
        for codebook_name, lookup in codebooks:
            is_fham_descriptor = codebook_name != "abdulsattar_arr4"
            if is_fham_descriptor:
                strategies = {
                    "exact_matching": ExactMatchMethod(descriptor=codebook_name),
                    "bounded_global_l1": BoundedAssignmentMethod(
                        bound, descriptor=codebook_name
                    ),
                    "unbounded_global_l1": OptimalAssignmentMethod(
                        descriptor=codebook_name
                    ),
                }
                stability_method = StabilityAwareAssignmentMethod(
                    bound, stability_aware_lambda, descriptor=codebook_name
                )
                stability_method.stabilities = _location_stabilities(
                    lookup, image, stability_dev_attacks, image_name
                )
                strategies["stability_aware"] = stability_method
                for method in strategies.values():
                    method.lookup_table = lookup.lookup_table
                    method.image_shape = lookup.image_shape
            else:
                bounded_ab = BoundedAssignmentMethod(bound)
                bounded_ab.lookup_table = lookup.lookup_table
                bounded_ab.image_shape = lookup.image_shape
                global_ab = OptimalAssignmentMethod()
                global_ab.lookup_table = lookup.lookup_table
                global_ab.image_shape = lookup.image_shape
                strategies = {
                    "exact_matching": lookup,
                    "bounded_global_l1": bounded_ab,
                    "unbounded_global_l1": global_ab,
                }

            for trial in range(trials):
                message = _message(length, image_name, trial)
                for strategy_name, method in strategies.items():
                    assignment = method.embed(message, image)
                    displacements = getattr(assignment, "displacements", None)
                    rows.append(
                        {
                            "image": image_name,
                            "codebook": codebook_name,
                            "strategy": strategy_name,
                            "length": length,
                            "trial": trial,
                            "success": int(assignment is not None),
                            "total_displacement": (
                                sum(map(abs, displacements))
                                if displacements
                                else (0 if assignment is not None else np.nan)
                            ),
                        }
                    )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["codebook", "strategy"], as_index=False).agg(
        trials=("success", "size"),
        success=("success", "mean"),
        mean_total_displacement=("total_displacement", "mean"),
    )
    return summary, raw


def _jpeg(array, quality):
    buffer = BytesIO()
    Image.fromarray(array).save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return np.asarray(Image.open(buffer).convert("L"))


def _resize(array, scale):
    side = max(1, round(array.shape[0] * scale))
    reduced = Image.fromarray(array).resize((side, side), Image.Resampling.LANCZOS)
    return np.asarray(
        reduced.resize((array.shape[1], array.shape[0]), Image.Resampling.LANCZOS)
    )


def _rotate(array, degrees):
    return np.asarray(
        Image.fromarray(array).rotate(
            degrees, resample=Image.Resampling.BILINEAR, fillcolor=0
        )
    )


def _gnoise(array, sigma, rng):
    return np.clip(
        array.astype(np.float64) + rng.normal(0, sigma, array.shape), 0, 255
    ).astype(np.uint8)


def _speckle(array, variance, rng):
    noise = rng.normal(0, np.sqrt(variance), array.shape)
    return np.clip(array.astype(np.float64) * (1 + noise), 0, 255).astype(np.uint8)


def _impulse(array, density, rng):
    attacked = array.copy()
    count = int(array.size * density / 2)
    indices = rng.choice(array.size, 2 * count, replace=False)
    attacked.flat[indices[:count]] = 0
    attacked.flat[indices[count:]] = 255
    return attacked


def _gfilter(array, kernel):
    sigma = 0.6 if kernel == 3 else 1.0
    return np.clip(
        gaussian_filter(array.astype(np.float64), sigma=sigma, radius=kernel // 2),
        0,
        255,
    ).astype(np.uint8)


def _medfilter(array, kernel):
    return median_filter(array, size=kernel).astype(np.uint8)


def _brightness(array, delta_pct):
    return np.clip(array.astype(np.float64) + delta_pct * 255, 0, 255).astype(np.uint8)


def _contrast(array, delta_pct):
    return np.clip(
        (array.astype(np.float64) - 128) * (1 + delta_pct) + 128, 0, 255
    ).astype(np.uint8)


def _gamma(array, value):
    normalized = array.astype(np.float64) / 255.0
    return np.clip(255 * (normalized ** value), 0, 255).astype(np.uint8)


def _crop_restore(array, pct):
    side = array.shape[0]
    margin = max(1, round(side * pct))
    cropped = array[margin : side - margin, margin : side - margin]
    return np.asarray(
        Image.fromarray(cropped).resize((side, side), Image.Resampling.LANCZOS)
    )


EXTENDED_TRANSFORMS = (
    "jpeg95", "jpeg90", "jpeg85", "jpeg75", "jpeg50",
    "resize075", "resize090", "resize110", "resize125",
    "rotate_neg1", "rotate_neg0_5", "rotate_pos0_5", "rotate_pos1",
    "gnoise_sigma0_5", "gnoise_sigma1", "gnoise_sigma2",
    "speckle_v0_001", "speckle_v0_005",
    "impulse_d0_001", "impulse_d0_005",
    "gfilter_k3", "gfilter_k5",
    "medfilter_k3", "medfilter_k5",
    "brightness_neg10", "brightness_pos10",
    "contrast_neg10", "contrast_pos10",
    "gamma_0_9", "gamma_1_1",
    "crop_restore_1pct", "crop_restore_5pct",
    "combo_jpeg90_resize090", "combo_jpeg90_gnoise1",
    "combo_resize090_gfilter3", "combo_jpeg85_brightness_pos10",
)


def _extended_attack(image, name, seed):
    rng = np.random.default_rng(seed)
    dispatch = {
        "jpeg95": lambda: _jpeg(image, 95),
        "jpeg90": lambda: _jpeg(image, 90),
        "jpeg85": lambda: _jpeg(image, 85),
        "jpeg75": lambda: _jpeg(image, 75),
        "jpeg50": lambda: _jpeg(image, 50),
        "resize075": lambda: _resize(image, 0.75),
        "resize090": lambda: _resize(image, 0.90),
        "resize110": lambda: _resize(image, 1.10),
        "resize125": lambda: _resize(image, 1.25),
        "rotate_neg1": lambda: _rotate(image, -1.0),
        "rotate_neg0_5": lambda: _rotate(image, -0.5),
        "rotate_pos0_5": lambda: _rotate(image, 0.5),
        "rotate_pos1": lambda: _rotate(image, 1.0),
        "gnoise_sigma0_5": lambda: _gnoise(image, 0.5, rng),
        "gnoise_sigma1": lambda: _gnoise(image, 1.0, rng),
        "gnoise_sigma2": lambda: _gnoise(image, 2.0, rng),
        "speckle_v0_001": lambda: _speckle(image, 0.001, rng),
        "speckle_v0_005": lambda: _speckle(image, 0.005, rng),
        "impulse_d0_001": lambda: _impulse(image, 0.001, rng),
        "impulse_d0_005": lambda: _impulse(image, 0.005, rng),
        "gfilter_k3": lambda: _gfilter(image, 3),
        "gfilter_k5": lambda: _gfilter(image, 5),
        "medfilter_k3": lambda: _medfilter(image, 3),
        "medfilter_k5": lambda: _medfilter(image, 5),
        "brightness_neg10": lambda: _brightness(image, -0.10),
        "brightness_pos10": lambda: _brightness(image, 0.10),
        "contrast_neg10": lambda: _contrast(image, -0.10),
        "contrast_pos10": lambda: _contrast(image, 0.10),
        "gamma_0_9": lambda: _gamma(image, 0.9),
        "gamma_1_1": lambda: _gamma(image, 1.1),
        "crop_restore_1pct": lambda: _crop_restore(image, 0.01),
        "crop_restore_5pct": lambda: _crop_restore(image, 0.05),
        "combo_jpeg90_resize090": lambda: _resize(_jpeg(image, 90), 0.90),
        "combo_jpeg90_gnoise1": lambda: _gnoise(_jpeg(image, 90), 1.0, rng),
        "combo_resize090_gfilter3": lambda: _gfilter(_resize(image, 0.90), 3),
        "combo_jpeg85_brightness_pos10": lambda: _brightness(_jpeg(image, 85), 0.10),
    }
    if name == "identity":
        return image
    if name not in dispatch:
        raise ValueError(f"unknown extended transform: {name}")
    return dispatch[name]()


def extended_transformation_robustness_experiment(
    images, transforms=("identity",) + EXTENDED_TRANSFORMS, length=100, trials=5, bound=2
):
    """Evaluates the 36-condition extended transformation matrix (5 JPEG
    qualities, 4 resize levels, 4 rotations, 3 Gaussian-noise levels, 2
    speckle levels, 2 impulse-noise densities, 2 Gaussian-filter kernels, 2
    median-filter kernels, 6 photometric changes, 2 crop-restore levels, and
    4 combined transforms) plus the identity reference, rather than the
    smaller 7-condition channel used elsewhere in this study."""
    rows = []
    for image_name, image in images.items():
        method = BoundedAssignmentMethod(bound)
        method.build_lookup_table(image)
        for trial in range(trials):
            message = _message(length, image_name, trial)
            assignment = method.embed(message, image)
            if assignment is None:
                continue
            for transform_name in transforms:
                seed = RANDOM_SEED + trial + zlib.crc32(
                    f"{image_name}:{transform_name}".encode()
                )
                attacked = (
                    image
                    if transform_name == "identity"
                    else _extended_attack(image, transform_name, seed)
                )
                recovered = method.extract(assignment, attacked)
                correct = sum(a == b for a, b in zip(message, recovered))
                rows.append(
                    {
                        "image": image_name,
                        "trial": trial,
                        "transform": transform_name,
                        "exact_recovery": int(recovered == message),
                        "character_accuracy": correct / length,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = raw.groupby("transform", as_index=False).agg(
        trials=("exact_recovery", "size"),
        exact_recovery=("exact_recovery", "mean"),
        character_accuracy=("character_accuracy", "mean"),
        character_accuracy_std=("character_accuracy", "std"),
    )
    return summary, raw


def _decoy_assignment(length, lookup, bound, rng):
    """A format- and length-matched decoy: `length` distinct locations drawn
    from the same codebook location pool as a real assignment, with random
    residuals in the same bound, but not tied to any real message. Used to
    build the H0 traffic-analysis class."""
    all_locations = [
        location
        for locations in lookup.lookup_table.values()
        for location in locations
    ]
    if length > len(all_locations):
        return None
    locations = rng.sample(all_locations, length)
    displacements = [rng.randint(-bound, bound) for _ in range(length)]
    return Assignment(lookup.image_shape, lookup.block_size, locations, displacements)


def traffic_detectability_experiment(
    images, lengths=(50, 100, 200), trials=40, bound=2, seed=RANDOM_SEED
):
    """H0-versus-H1 traffic-analysis check. H1 traces are real protected
    envelopes (``AuxiliaryChannel.protect``) of genuine FHAM assignments; H0
    traces are protected envelopes of a format- and length-matched decoy
    assignment (same record count, same residual bound, random content) for
    the same image and length, so that the two classes cannot be separated
    by record count alone (the envelope header's raw-size field is
    identical by construction). Four classifiers (logistic regression,
    random forest, gradient boosting, MLP) are trained on the only features
    an observer could measure without breaking AES-GCM -- envelope size and
    processing time -- with a single stratified train/test split (no
    hyperparameter tuning, so no separate validation split is used). This
    tests empirical distinguishability of ciphertext-level ``size, timing``
    traces at matched message length, not general traffic undetectability.
    For the shaped mode, the observable timing feature models fixed-cadence
    transport and is therefore constant; the raw local protection time is
    still recorded separately as ``crypto_time_ms``. The message length
    itself is already shown to leak through observable envelope size in
    ``leakage_experiment``."""
    key = os.urandom(32)
    shaped_record_capacity = max(lengths)
    rows = []
    for image_name, image in images.items():
        method = BoundedAssignmentMethod(bound)
        method.build_lookup_table(image)
        for length in lengths:
            for trial in range(trials):
                message = _message(length, image_name, trial)
                assignment = method.embed(message, image)
                if assignment is None:
                    continue

                decoy_seed = seed + trial * 97 + length * 1009 + zlib.crc32(
                    image_name.encode()
                )
                decoy = _decoy_assignment(
                    length, method, bound, random.Random(decoy_seed)
                )
                if decoy is None:
                    continue

                for envelope_mode in ("compact", "shaped"):
                    if envelope_mode == "compact":
                        protect = lambda item: AuxiliaryChannel.protect(item, key)
                    else:
                        protect = lambda item: AuxiliaryChannel.protect_shaped(
                            item, key, shaped_record_capacity
                        )

                    start = time.perf_counter()
                    envelope_h1 = protect(assignment)
                    crypto_time_h1_ms = (time.perf_counter() - start) * 1000
                    observable_time_h1_ms = (
                        0.0 if envelope_mode == "shaped" else crypto_time_h1_ms
                    )
                    rows.append(
                        {
                            "envelope_mode": envelope_mode,
                            "label": 1,
                            "image": image_name,
                            "length": length,
                            "trial": trial,
                            "record_capacity": (
                                shaped_record_capacity
                                if envelope_mode == "shaped"
                                else len(assignment.locations)
                            ),
                            "size": len(envelope_h1),
                            "time_ms": observable_time_h1_ms,
                            "crypto_time_ms": crypto_time_h1_ms,
                        }
                    )

                    start = time.perf_counter()
                    envelope_h0 = protect(decoy)
                    crypto_time_h0_ms = (time.perf_counter() - start) * 1000
                    observable_time_h0_ms = (
                        0.0 if envelope_mode == "shaped" else crypto_time_h0_ms
                    )
                    rows.append(
                        {
                            "envelope_mode": envelope_mode,
                            "label": 0,
                            "image": image_name,
                            "length": length,
                            "trial": trial,
                            "record_capacity": (
                                shaped_record_capacity
                                if envelope_mode == "shaped"
                                else len(decoy.locations)
                            ),
                            "size": len(envelope_h0),
                            "time_ms": observable_time_h0_ms,
                            "crypto_time_ms": crypto_time_h0_ms,
                        }
                    )

    raw = pd.DataFrame(rows)
    summary_rows = []
    for envelope_mode, mode_raw in raw.groupby("envelope_mode", sort=False):
        strata = mode_raw["label"].astype(str) + "-" + mode_raw["length"].astype(str)
        train_df, test_df = train_test_split(
            mode_raw, test_size=0.3, stratify=strata, random_state=seed
        )

        feature_cols = ["length", "size", "time_ms"]
        x_train, y_train = train_df[feature_cols], train_df["label"]
        x_test, y_test = test_df[feature_cols], test_df["label"]

        classifiers = {
            "logistic_regression": LogisticRegression(max_iter=1000),
            "random_forest": RandomForestClassifier(n_estimators=200, random_state=seed),
            "gradient_boosting": GradientBoostingClassifier(random_state=seed),
            "mlp": MLPClassifier(
                hidden_layer_sizes=(16,), max_iter=2000, random_state=seed
            ),
        }

        for name, clf in classifiers.items():
            clf.fit(x_train, y_train)
            proba = clf.predict_proba(x_test)[:, 1]
            preds = clf.predict(x_test)
            auc = roc_auc_score(y_test, proba)
            balanced_accuracy = balanced_accuracy_score(y_test, preds)
            fpr, tpr, _ = roc_curve(y_test, proba)
            low_fpr = fpr <= 0.05
            tpr_at_5pct_fpr = float(tpr[low_fpr].max()) if low_fpr.any() else 0.0
            summary_rows.append(
                {
                    "envelope_mode": envelope_mode,
                    "classifier": name,
                    "n_train": len(train_df),
                    "n_test": len(test_df),
                    "auc": auc,
                    "balanced_accuracy": balanced_accuracy,
                    "tpr_at_5pct_fpr": tpr_at_5pct_fpr,
                }
            )
        summary_rows.append(
            {
                "envelope_mode": envelope_mode,
                "classifier": "random_baseline",
                "n_train": len(train_df),
                "n_test": len(test_df),
                "auc": 0.5,
                "balanced_accuracy": 0.5,
                "tpr_at_5pct_fpr": 0.05,
            }
        )
    summary = pd.DataFrame(summary_rows)
    return summary, raw


GEOMETRIC_TRANSFORMS = (
    "rotate_neg1", "rotate_neg0_5", "rotate_pos0_5", "rotate_pos1",
    "crop_restore_1pct", "crop_restore_5pct",
)


def ecc_repetition_experiment(
    images,
    repeats=(1, 3, 5),
    transforms=("identity",) + EXTENDED_TRANSFORMS,
    length=40,
    trials=20,
    bound=2,
):
    """Evaluates a message-layer repetition-code error-correction wrapper
    (``fham.ecc.repetition_encode``/``repetition_decode``) against the same
    extended 36-condition transformation matrix used by
    ``extended_transformation_robustness_experiment``, at repeat factors
    ``repeats``. The descriptor and ``Location`` model are unchanged: each
    repeat factor only expands the embedded message and majority-decodes
    the recovered one, at a capacity cost of one usable character per
    ``repeat`` locations consumed.

    This targets value-domain transformation sensitivity (JPEG, additive
    noise, filtering, resizing, photometric change): redundancy corrects a
    minority of corrupted copies. It is not expected to, and empirically
    does not, help under geometric misalignment (``GEOMETRIC_TRANSFORMS``:
    rotation and crop-restore), because those transforms decorrelate the
    recomputed descriptor from its embed-time value at a fixed location, so
    majority vote over decorrelated copies stays decorrelated rather than
    converging on the original symbol."""
    rows = []
    for image_name, image in images.items():
        method = BoundedAssignmentMethod(bound)
        method.build_lookup_table(image)
        for trial in range(trials):
            message = _message(length, image_name, trial)
            for repeat in repeats:
                expanded_message = repetition_encode(message, repeat)
                assignment = method.embed(expanded_message, image)
                if assignment is None:
                    continue
                for transform_name in transforms:
                    seed = RANDOM_SEED + trial + zlib.crc32(
                        f"{image_name}:{transform_name}:ecc{repeat}".encode()
                    )
                    attacked = (
                        image
                        if transform_name == "identity"
                        else _extended_attack(image, transform_name, seed)
                    )
                    recovered_expanded = method.extract(assignment, attacked)
                    recovered = repetition_decode(recovered_expanded, length, repeat)
                    correct = sum(a == b for a, b in zip(message, recovered))
                    rows.append(
                        {
                            "image": image_name,
                            "trial": trial,
                            "transform": transform_name,
                            "repeat": repeat,
                            "domain": (
                                "geometric"
                                if transform_name in GEOMETRIC_TRANSFORMS
                                else "identity"
                                if transform_name == "identity"
                                else "value"
                            ),
                            "exact_recovery": int(recovered == message),
                            "character_accuracy": correct / length,
                        }
                    )
    raw = pd.DataFrame(rows)
    summary = raw.groupby(["repeat", "domain"], as_index=False).agg(
        trials=("exact_recovery", "size"),
        exact_recovery=("exact_recovery", "mean"),
        character_accuracy=("character_accuracy", "mean"),
    )
    return summary, raw
