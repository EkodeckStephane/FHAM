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


def _register(reference, attacked):
    reference_float = reference.astype(np.float32) / 255.0
    attacked_float = attacked.astype(np.float32) / 255.0
    ref_orb, atk_orb = ORB(n_keypoints=800, fast_threshold=0.04), ORB(
        n_keypoints=800, fast_threshold=0.04
    )
    ref_orb.detect_and_extract(reference_float)
    atk_orb.detect_and_extract(attacked_float)
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
    transforms = {
        "rotate_pos1": lambda x: _rotate(x, 1.0),
        "crop_restore_5pct": lambda x: _crop_restore(x, 0.05),
    }
    for path in sorted((DATASET_DIR / "controlled").glob("*.png")):
        name = path.stem
        image = np.asarray(Image.open(path).convert("L"))
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        for trial in range(5):
            message = _message(40, name, trial)
            assignment = method.embed(message, image)
            if assignment is None:
                continue
            for transform_name, transform in transforms.items():
                attacked = transform(image)
                fixed_recovered = method.extract(assignment, attacked)
                restored, matches, inliers = _register(image, attacked)
                recovered = (method.extract(assignment, restored)
                             if restored is not None else "")
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
    )
    summary.to_csv(RESULTS_DIR / "geometry_registration_pilot.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
