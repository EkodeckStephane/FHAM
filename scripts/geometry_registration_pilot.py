"""Small exploratory ORB/RANSAC registration pilot for FHAM geometry attacks."""

import numpy as np
import pandas as pd
from PIL import Image
from skimage.feature import ORB, match_descriptors
from skimage.measure import ransac
from skimage.transform import ProjectiveTransform, warp

from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _crop_restore, _message, _rotate
from fham.methods import BoundedAssignmentMethod


def _features(image):
    orb = ORB(n_keypoints=600, fast_threshold=0.04)
    try:
        orb.detect_and_extract(image.astype(np.float32) / 255.0)
    except RuntimeError:
        return None
    return orb


def _register(reference, attacked, ref_orb, atk_orb):
    if (ref_orb is None or atk_orb is None
            or len(ref_orb.descriptors) < 4 or len(atk_orb.descriptors) < 4):
        return None, 0, 0
    pairs = match_descriptors(ref_orb.descriptors, atk_orb.descriptors,
                              cross_check=True, max_ratio=0.8)
    if len(pairs) < 4:
        return None, len(pairs), 0
    source = ref_orb.keypoints[pairs[:, 0]][:, ::-1]
    destination = atk_orb.keypoints[pairs[:, 1]][:, ::-1]
    model, inliers = ransac(
        (source, destination), ProjectiveTransform,
        min_samples=4, residual_threshold=3, max_trials=1000,
        rng=np.random.default_rng(20261110),
    )
    if model is None or inliers is None or int(inliers.sum()) < 4:
        return None, len(pairs), 0
    restored = warp(
        attacked, inverse_map=model, output_shape=reference.shape,
        order=1, mode="constant", cval=0, preserve_range=True,
    ).clip(0, 255).astype(np.uint8)
    return restored, len(pairs), int(inliers.sum())


def main():
    rows = []
    query_images = {}
    for path in sorted((DATASET_DIR / "controlled").glob("*.png")):
        query_images[path.stem] = np.asarray(Image.open(path).convert("L"))
    gallery = {}
    for path in sorted((DATASET_DIR / "stress").glob("*.png")):
        gallery[path.stem] = np.asarray(Image.open(path).convert("L"))
    gallery_features = {name: _features(image) for name, image in gallery.items()}
    transforms = {
        "rotate_pos1": lambda x: _rotate(x, 1.0),
        "crop_restore_5pct": lambda x: _crop_restore(x, 0.05),
    }
    for name, image in query_images.items():
        if name not in gallery or not np.array_equal(image, gallery[name]):
            raise ValueError(f"query reference {name!r} is not identical in catalog")
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        transform_results = {}
        for transform_name, transform in transforms.items():
            attacked = transform(image)
            attacked_features = _features(attacked)
            restored, matches, inliers = _register(
                image, attacked, gallery_features[name], attacked_features
            )
            match_counts = []
            for candidate_name in gallery:
                candidate_features = gallery_features[candidate_name]
                if (candidate_features is None or attacked_features is None
                        or len(candidate_features.descriptors) < 4
                        or len(attacked_features.descriptors) < 4):
                    match_counts.append((0, candidate_name))
                    continue
                pairs = match_descriptors(
                    candidate_features.descriptors,
                    attacked_features.descriptors,
                    cross_check=True,
                    max_ratio=0.8,
                )
                match_counts.append((len(pairs), candidate_name))
            retrieval = []
            for _count, candidate_name in sorted(match_counts, reverse=True)[:10]:
                if _count < 4:
                    continue
                _candidate_aligned, candidate_matches, candidate_inliers = _register(
                    gallery[candidate_name],
                    attacked,
                    gallery_features[candidate_name],
                    attacked_features,
                )
                retrieval.append((candidate_inliers, candidate_matches, candidate_name))
            retrieved_name = max(retrieval)[2]
            transform_results[transform_name] = (
                attacked, restored, matches, inliers, retrieved_name
            )
        for trial in range(5):
            message = _message(40, name, trial)
            assignment = method.embed(message, image)
            if assignment is None:
                continue
            for transform_name in transforms:
                attacked, restored, matches, inliers, retrieved_name = transform_results[
                    transform_name
                ]
                fixed_recovered = method.extract(assignment, attacked)
                recovered = (method.extract(assignment, restored)
                             if restored is not None else "")
                retrieved_message = (
                    method.extract(assignment, query_images[retrieved_name])
                    if retrieved_name == name else ""
                )
                rows.append({
                    "image": name, "trial": trial,
                    "transform": transform_name,
                    "keypoint_matches": matches,
                    "ransac_inliers": inliers,
                    "registration_success": int(restored is not None),
                    "fixed_coordinate_exact_recovery": int(fixed_recovered == message),
                    "fixed_coordinate_accuracy": (
                        sum(a == b for a, b in zip(message, fixed_recovered)) / len(message)
                    ),
                    "exact_message_recovery": int(recovered == message),
                    "character_accuracy": (
                        sum(a == b for a, b in zip(message, recovered)) / len(message)
                    ),
                    "catalog_identification_success": int(retrieved_name == name),
                    "catalog_canonical_exact_recovery": int(
                        retrieved_message == message
                    ),
                    "catalog_size": len(gallery),
                })
    raw = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_csv(RESULTS_DIR / "geometry_registration_pilot_raw.csv", index=False)
    summary = raw.groupby("transform", as_index=False).agg(
        trials=("trial", "count"),
        mean_matches=("keypoint_matches", "mean"),
        mean_inliers=("ransac_inliers", "mean"),
        registration_rate=("registration_success", "mean"),
        fixed_coordinate_exact_rate=("fixed_coordinate_exact_recovery", "mean"),
        fixed_coordinate_accuracy=("fixed_coordinate_accuracy", "mean"),
        exact_recovery_rate=("exact_message_recovery", "mean"),
        mean_character_accuracy=("character_accuracy", "mean"),
        catalog_canonical_exact_recovery_rate=(
            "catalog_canonical_exact_recovery", "mean"
        ),
        catalog_size=("catalog_size", "first"),
    )
    unique_queries = raw.drop_duplicates(["image", "transform"])
    retrieval = unique_queries.groupby("transform", as_index=False).agg(
        catalog_queries=("image", "count"),
        catalog_identification_rate=("catalog_identification_success", "mean"),
    )
    summary = summary.merge(retrieval, on="transform", validate="one_to_one")
    summary.to_csv(RESULTS_DIR / "geometry_registration_pilot.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
