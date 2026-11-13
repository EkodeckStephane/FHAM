# FHAM TLS detectability against captured NonVPN traffic

## Question and experiment

This experiment tests whether a passive observer can distinguish the current
FHAM TLS application exchange from unrelated captured TLS sessions using only
directional TLS-record sizes. It extends the local matched-HTTP experiment:
the negative class is now real, unmatched application traffic rather than a
control deliberately constructed to match FHAM byte-for-byte.

The positive class consists of the 240 FHAM TLS 1.3/TCP flows already measured
with real local sockets: 80 flows in each of three independent runs, with 40-
and 200-character messages and eight covers. The negative class was extracted
from the 109 PCAP/PCAPNG files in the ISCXVPN2016 NonVPN archives at
`D:\dataset`. The parser reassembled TCP payloads and retained flows containing
at least three coherent TLS records across both directions. It found 1,946
candidate TLS flows in 91 captures; 18 captures had no retained TLS flow.
The corpus includes labeled application captures such as email, messaging,
file transfer, streaming, and VoIP.

The detector excludes TLS version, addresses, ports, packet timing, and
payload contents. No IP addresses, ports, packet payloads, or ciphertext were
saved in the feature file. A logistic-regression detector was trained on two complete FHAM
runs and tested on the held-out third run. In the same fold, one third of the
background capture files was held out as complete capture groups. This was
repeated for all three positive runs. Metrics use FHAM as the positive class.
We compared directional byte/record counts, the first one or four record
lengths, and the combination of directional counts/volume with the first
sixteen record lengths per direction.

## Results

| Held-out FHAM run | Background captures / TLS flows | Directional volume AUC | First record AUC | First four records AUC | Volume + first sixteen lengths AUC | Full-feature balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|
| rep1 | 31 / 702 | 0.830 | 0.648 | 0.883 | 0.957 | 0.923 |
| rep2 | 30 / 570 | 0.881 | 0.679 | 0.905 | 0.986 | 0.957 |
| rep3 | 30 / 674 | 0.892 | 0.601 | 0.921 | 0.985 | 0.960 |
| **Mean** | **30.3 / 649** | **0.868** | **0.643** | **0.903** | **0.976** | **0.947** |

The TLS FHAM exchange was readily distinguishable from these unmatched
captured flows using record lengths alone. Directional volume already gave
mean AUC 0.868; the first four record lengths gave 0.903; combining
directional volume with the first sixteen record lengths gave 0.976. This
establishes a concrete detectability risk in the tested
FHAM transport profile. It is consistent with the matched-control result:
matching the HTTP control's directional byte totals and TLS record-length
sequences removed this separation, while ordinary traffic does not share those
engineered sizes and response pattern by construction.

## Interpretation and scope

The result demonstrates detection against a diverse, labeled NonVPN corpus;
it does not estimate false-positive rates in a continuously mixed modern
network. ISCXVPN2016 contains application-oriented captures from 2016, and the
capture groups are not independent organizations or network environments.
The local FHAM TLS endpoint and application framing are also part of the
positive fingerprint. The experiment therefore evaluates this concrete
end-to-end transport profile, rather than isolating the assignment algorithm
from its framing, acknowledgement, and TLS implementation.

The strongest next mitigation is to make the complete exchange conform to a
chosen host application's ordinary request/response size and record-length
distribution, including replies and session setup, then repeat this held-out
capture test against modern mixed traffic. Padding a single request is not
sufficient: the reply volume, record sequence, timing, and TLS-stack fingerprint
must also be considered. The matched HTTP control is a useful proof that size
matching can remove the measured signal in a controlled pair; the new result
shows that this property has not yet been achieved against unrelated traffic.

## Reproduction

Run the full PCAP scan and grouped evaluation:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --background D:\dataset
```

Recompute the grouped detector from the extracted aggregate features:

```powershell
python scripts/evaluate_nonvpn_tls_detectability.py --reuse-extracted
```

Outputs:

- `results/nonvpn_tls_flow_features.csv` — aggregate TLS sequence features by
  capture and flow, with no addresses or payloads.
- `results/nonvpn_tls_detectability_cv.csv` — held-out results for all three
  folds and four feature sets.
- `scripts/evaluate_nonvpn_tls_detectability.py` — extraction and evaluation.
