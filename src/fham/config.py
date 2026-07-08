from pathlib import Path

BLOCK_SIZE = 24
IMAGE_SIZE = 512
PRINTABLE_ASCII = tuple(range(32, 127))
MESSAGE_LENGTHS = (10, 20, 30, 40, 50, 60, 80, 100, 150, 200)
RANDOM_SEED = 42

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
PAPER_DIR = ROOT / "paper"
COVER_DIR = PAPER_DIR / "cover"
DATASET_DIR = ROOT / "dataset"
