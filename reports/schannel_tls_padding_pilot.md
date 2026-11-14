# Empirical TLS record padding and fragmentation pilot

## Question

The unmatched-capture detector identifies a network-level signal in the FHAM
transport profile. This follow-up tests a concrete mitigation: retain the
original FHAM offer and protected record, append a framed padding record, and
fragment the resulting application streams to match record counts and
directional TLS byte totals sampled from independent training captures.

The client uses Windows Schannel through .NET `SslStream` with TLS 1.2. Each
paired FHAM/HTTP exchange uses a prewarmed resumable session. The HTTP control
matches the shaped FHAM request and response lengths and write boundaries. A
transparent local TCP relay records TLS record lengths and direction only.

## Capture separation and procedure

The 91 capture groups with candidate TLS flows were sorted by capture name.
Every third group (31 captures) supplied shape templates. The remaining 60
groups (1,244 TLS flows) formed the evaluation background. Thus, no capture
used to choose a FHAM padding target appears in the held-out background set.
Within those 60 evaluation captures, the detector held out 20 complete capture
groups and one complete FHAM run in each fold.

Each of three independent runs contains 80 FHAM/HTTP pairs across 40- and
200-character messages and eight covers. The three runs produced 240 pairs
(480 TLS sessions). All 240 FHAM messages passed exact-recovery verification
before transport. In every pair, FHAM and HTTP had identical directional TLS
byte totals and identical record-length sequences. For each shaped FHAM flow,
the directional TLS byte totals and record counts also matched the selected
training template exactly. The padding frame preserved the original offer and
protected-record frames when parsed from the resulting application stream.

## Held-out detector results

| Profile | Byte totals AUC | Record counts AUC | Counts + bytes AUC | First record AUC | First four records AUC | Counts + bytes + first 16 AUC |
|---|---:|---:|---:|---:|---:|---:|
| Schannel TLS 1.2, unshaped | 0.888 | 0.909 | 0.929 | 0.686 | 0.904 | 0.974 |
| Schannel TLS 1.2, padded and fragmented | 0.747 | 0.594 | 0.781 | 0.686 | 0.923 | 0.955 |

Both profiles use the same 60-capture evaluation set, classifier, group split,
and positive-run holdout. The empirical padding and fragmentation reduced the
mean AUC of the byte-total and record-count detector from 0.929 to 0.781. The
full first-sixteen-record detector remained at 0.955. The first four records
also remained strongly discriminative, showing that application-level padding
does not mask the fixed TLS handshake and early-record pattern in this local
endpoint profile.

This is a working mitigation for the measured size and record-count signals,
with a measurable reduction in their classifier performance. It does not yet
remove the early TLS-record-length signal. The result provides a concrete
baseline for the next transport iteration: shape the connection setup and TLS
endpoint profile together with the FHAM request, response, and padding.

## Reproduction

Extract the NonVPN background once using:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --background D:\dataset
```

Run all three unshaped Schannel profiles and all three shaped profiles:

```powershell
python scripts/socket_schannel_detectability_pilot.py --run-id rep1
python scripts/socket_schannel_detectability_pilot.py --run-id rep2
python scripts/socket_schannel_detectability_pilot.py --run-id rep3
python scripts/socket_schannel_detectability_pilot.py --run-id rep1 --shape-to-background
python scripts/socket_schannel_detectability_pilot.py --run-id rep2 --shape-to-background
python scripts/socket_schannel_detectability_pilot.py --run-id rep3 --shape-to-background
```

The shaped run writes the 60-capture evaluation set to
`results/nonvpn_tls_flow_features_eval.csv` and the 31 template group names to
`results/nonvpn_tls_shape_template_groups.txt`. Evaluate both profiles against
that disjoint set:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --background-features results\nonvpn_tls_flow_features_eval.csv --positive-profile schannel_tls12 --positive-prefix schannel_tls_flows --cv-output schannel_tls12_eval60_cv.csv
python scripts/evaluate_nonvpn_tls_detectability.py --background-features results\nonvpn_tls_flow_features_eval.csv --positive-profile schannel_tls12_shaped --positive-prefix schannel_shaped_tls_flows --cv-output shaped_tls12_detectability_cv.csv
```

The flow CSVs contain aggregate features only. Temporary padding payloads and
test-certificate files are removed after each run.
