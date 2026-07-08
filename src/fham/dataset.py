import csv

import numpy as np
from PIL import Image
from skimage import data

from .config import COVER_DIR, DATASET_DIR, IMAGE_SIZE


LOADERS = {
    "camera": data.camera,
    "astronaut": data.astronaut,
    "chelsea": data.chelsea,
    "coffee": data.coffee,
    "coins": data.coins,
    "moon": data.moon,
    "clock": data.clock,
    "page": data.page,
}

EVALUATION_LOADERS = {
    **LOADERS,
    "brick": data.brick,
    "grass": data.grass,
    "gravel": data.gravel,
    "horse": data.horse,
    "hubble": data.hubble_deep_field,
    "immunohistochemistry": data.immunohistochemistry,
    "logo": data.logo,
    "retina": data.retina,
    "rocket": data.rocket,
    "text": data.text,
    "colorwheel": data.colorwheel,
}

SOURCE_METADATA = {
    "camera": ("scikit-image:data.camera", "photograph"),
    "astronaut": ("scikit-image:data.astronaut", "photograph"),
    "chelsea": ("scikit-image:data.chelsea", "photograph"),
    "coffee": ("scikit-image:data.coffee", "photograph"),
    "coins": ("scikit-image:data.coins", "photograph"),
    "moon": ("scikit-image:data.moon", "scientific photograph"),
    "clock": ("scikit-image:data.clock", "photograph"),
    "page": ("scikit-image:data.page", "scanned document"),
    "brick": ("scikit-image:data.brick", "texture photograph"),
    "grass": ("scikit-image:data.grass", "texture photograph"),
    "gravel": ("scikit-image:data.gravel", "texture photograph"),
    "horse": ("scikit-image:data.horse", "binary silhouette"),
    "hubble": ("scikit-image:data.hubble_deep_field", "scientific photograph"),
    "immunohistochemistry": (
        "scikit-image:data.immunohistochemistry",
        "microscopy image",
    ),
    "logo": ("scikit-image:data.logo", "graphic"),
    "retina": ("scikit-image:data.retina", "medical photograph"),
    "rocket": ("scikit-image:data.rocket", "photograph"),
    "text": ("scikit-image:data.text", "scanned document"),
    "colorwheel": ("scikit-image:data.colorwheel", "synthetic graphic"),
}


def _prepare(image):
    image = np.asarray(image)
    if image.ndim == 3:
        image = image[..., :3].mean(axis=2)
    if image.dtype == bool:
        image = image.astype(np.uint8) * 255
    elif np.issubdtype(image.dtype, np.floating):
        scale = 255 if image.max() <= 1 else 1
        image = np.clip(image * scale, 0, 255).astype(np.uint8)
    else:
        image = image.astype(np.uint8)
    return np.asarray(
        Image.fromarray(image).resize(
            (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
        )
    )


def _save_dataset(images, subset, metadata):
    directory = DATASET_DIR / subset
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, image in images.items():
        filename = f"{name}.png"
        Image.fromarray(image).save(directory / filename)
        source, content_type = metadata[name]
        rows.append(
            {
                "file": filename,
                "name": name,
                "subset": subset,
                "source": source,
                "content_type": content_type,
                "width": image.shape[1],
                "height": image.shape[0],
                "channels": 1,
                "preprocessing": "grayscale conversion and Lanczos resize",
            }
        )
    with (directory / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def standard_images():
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    images = {}
    for name, loader in LOADERS.items():
        image = _prepare(loader())
        Image.fromarray(image).save(COVER_DIR / f"{name}.png")
        images[name] = image
    _save_dataset(
        images,
        "controlled",
        {name: SOURCE_METADATA[name] for name in images},
    )
    return images


def evaluation_images():
    images = {name: _prepare(loader()) for name, loader in EVALUATION_LOADERS.items()}
    metadata = {name: SOURCE_METADATA[name] for name in images}
    for index, face in enumerate(data.lfw_subset()):
        name = f"lfw_{index:03d}"
        images[name] = _prepare(face)
        metadata[name] = (
            "scikit-image:data.lfw_subset (Labeled Faces in the Wild)",
            "face photograph",
        )
    _save_dataset(images, "stress", metadata)
    return images
