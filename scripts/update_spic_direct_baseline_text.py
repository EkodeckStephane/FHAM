from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "source" / "FHAM_SPIC_article.tex",
    ROOT / "FHAM_Elsevier_SPIC" / "01_MAIN_MANUSCRIPT" / "02_REVISION_SOURCE" / "FHAM_SPIC_article.tex",
)
REPLACEMENTS = (
    ("242.10 bytes", "230.10 bytes"),
    ("242.10-byte", "230.10-byte"),
    ("$200/242.10=82.6\\%$", "$200/230.10=86.9\\%$"),
    ("corresponding to 2.27 times", "corresponding to 2.39 times"),
    ("corresponding to 3.52 times", "corresponding to 3.70 times"),
    ("a ratio of 2.27 (Table", "a ratio of 2.39 (Table"),
    ("is 157 bytes.", "is 145 bytes."),
    ("baseline is\n53 bytes.", "baseline is\n41 bytes."),
    ("53--252 bytes", "41--240 bytes"),
)

for path in TARGETS:
    text = path.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        if old not in text:
            raise RuntimeError(f"expected phrase not found in {path.name}: {old!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8", newline="")
    print(path)
