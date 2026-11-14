# FHAM parameter and payload ablation

## Question and evaluation design

This ablation screens parameters that affect bounded assignment feasibility and the auxiliary record: descriptor family, block size, displacement bound $B$, message family and length, and lossless zlib level-9 preprocessing. It evaluates feasibility separately from post-transformation recovery. Fixed seeded messages are used throughout. The selected spectral $12\times12$ profile is screened on the eight controlled images, evaluated on 200 LFW face images (three messages per family), and then checked on a separate 11-image non-face scene subset (three messages per family). The scene subset is small and serves as a transfer check, not a broad population estimate.

The stability-weight sweep uses spectral $12\times12$ blocks, $B=2$, and three templated 200-byte messages per scene image. JPEG 90, resize 90, and noise level 1 form the development transformations; JPEG 75, rotation by $1^\circ$, and noise level 2 form the evaluation transformations. There are 33 assignments per weight and 99 transformed evaluations.

## Capacity findings

On 200 LFW covers, at $B=2$, zlib preprocessing changes repeated-byte feasibility from 0% to 97.8%, and templated-text feasibility from 80.5% to 92.2%. For printable ASCII it changes 88.3% to 90.5%; for uniform bytes it remains 88.7%. The corresponding compressed lengths are 12, 116, 201, and 211 bytes from 200-byte sources. Compression expands the latter two families and provides no practical capacity gain for them.

Raising $B$ to 4 yields compressed feasibility rates of 98.5%, 97.2%, 96.3%, and 97.2% for repeated, templated, printable, and uniform messages. At $B=8$ the respective rates are 99.3%, 98.3%, 98.0%, and 98.0%. The independent 11-scene holdout at $B=2$ gives 100%, 97.0%, 90.9%, and 90.9%; at $B=4$ it gives 100%, 100%, 97.0%, and 100%. These gains are assignment feasibility on the original cover, not exact recovery after image transformation.

The smaller spectral block profile increases the controlled codebook from 1,764 locations at block size 24 to 7,056 at block size 12, while mean construction time rises from 121 ms to 428 ms. Thus, the selected operating point trades computation for denser location capacity. It is an empirically selected profile for the tested corpus and message mix, not a universal optimum.

## Metadata cost

For compressed 200-byte messages at spectral block size 12 and $B=2$, the current compact record averages 97.92, 349.79, 535.92, and 557.08 bytes for repeated, templated, printable, and uniform inputs. A packed fixed-width prototype reduces these to 87.00, 284.92, 422.88, and 438.17 bytes. Direct AES-GCM protection of the same preprocessed message is 53, 157, 242, and 252 bytes. The packed FHAM record therefore remains 1.64--1.82 times larger than direct protection across these families. The prototype saves roughly 18--25% against the current compact record; it does not reverse the direct-encryption comparison. A fixed 200-record shaped envelope is 852 bytes and hides the tested length class while increasing transmitted volume.

## Stability-weight transfer

All five tested weights have 32 feasible assignments out of 33. Weights 0.25, 0.50, and 0.75 yield the same mean displacement (21.97) and nearly identical character accuracy: 57.8% under JPEG 75, 68.1% under noise level 2, and 9.4% under rotation by $1^\circ$. Weight 1.0 lowers displacement to 2.78 but reduces those accuracies to 29.2%, 38.1%, and 3.8%. Weight 0.0 has mean displacement 211.47 and similar character accuracy to the middle region. Exact source recovery is 0/99 for every weight under the evaluation transformations. This small transfer sample supports a middle operating region for the tested transformations; it does not establish a unique or distribution-independent best weight.

## Interpretation and remaining limits

Compression and parameter selection materially improve assignment feasibility for low-entropy messages and some scene inputs. They do not make FHAM metadata more compact than direct AES-GCM protection of the same compressed payload. AUC after the measured padding and fragmentation profile remains 0.781 for byte totals plus record counts and 0.955 when the first 16 TLS record lengths are added. The security experiment is therefore a quantified detector evaluation on a specific captured-flow corpus, not a general claim of network undetectability. Geometric transformations continue to produce zero exact recovery in the evaluated registration pilot. These limits require changes to record representation, traffic shaping, or synchronization design; parameter tuning alone does not remove them.

## Reproduction files

The paired scripts `scripts/parameter_ablation_revision.py` and `scripts/lambda_transfer_ablation.py` generate the grouped and trial-level outputs in `results/revision_ablation/`. Per-run JSON files record command lines, image and message digests, parameter grids, and trial counts. The manuscript tables report assignment feasibility separately from transformed-channel recovery.
