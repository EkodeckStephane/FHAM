# SPIC manuscript and revision package

This directory contains the original manuscript supplied for revision and the
current revision package for *Signal Processing: Image Communication*.

## Contents

- `original/`: original manuscript PDF and its LaTeX source/dependencies.
- `revised/`: revised manuscript PDF and editable LaTeX source/dependencies.
- `review/`: point-by-point response, revision cover letter, Highlights, and
  the blue-only PDF comparison. The comparison suppresses removed passages.
- `supplementary/`: Supplementary Material S1 and the two S2 evidence archives.

The large base S2 archive is stored with Git LFS. The companion S2 archive
contains the V1 authenticated-record implementation and the security and
endpoint-observation results cited in the revised manuscript. Third-party
image datasets and capture payloads remain with their original distributors.

## Reproduction

Compile the revised article from `revised/source/FHAM_SPIC_article.tex` with
pdfLaTeX; the folder contains the class, figures, and table sources. The
original source in `original/source/` has the same dependencies. S1 describes
the evidence scope and the S2 archives contain the result data and scripts.

## Revision scope

The manuscript reports the assignment, recovery, authenticated-record, and
network-observation findings under their measured conditions. It states the
remaining limits for image-only classification under message-conditioned
cover selection, external monotonic-epoch dependence, and production key
lifecycle explicitly.
