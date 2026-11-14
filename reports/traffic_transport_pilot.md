# Synthetic FHAM transport pilot

## Purpose and profile

This pilot compares controlled positive FHAM application exchanges with the
reassembled TCP-flow background from the ISCXVPN2016 NonVPN archives. It
generates synthetic captures for two transport profiles:

- `raw_tcp`: the experimental application frames are visible directly in TCP
  payloads. This is an intentionally visible positive control, not a secure
  transport recommendation.
- `tls13_tcp`: the same application exchange is carried by an actual local
  TLS 1.3 memory-BIO session. The synthetic client validates the locally pinned
  test certificate. The packet capture is synthesized from that session's
  TLS records; no service was deployed and no live network traffic was
  recorded.

For each mode, the run generated 40 flows at 40 characters and 40 flows at
200 characters, over eight controlled covers. The application-level checks
verified message recovery, signed ephemeral key offers, key agreement,
cover binding, and sequence acceptance in all 80 trials per mode.

## Results

| Profile | Characters | Flows | Exact app recovery | Versioned frame marker in stream | Median packets | Median IP bytes | Median TCP payload bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Raw TCP | 40 | 40 | 40/40 | 40/40 | 8 | 837 | 517 |
| Raw TCP | 200 | 40 | 40/40 | 40/40 | 8 | 1,477 | 1,157 |
| TLS 1.3/TCP | 40 | 40 | 40/40 | 0/40 | 13 | 3,261 | 2,741 |
| TLS 1.3/TCP | 200 | 40 | 40/40 | 0/40 | 13 | 3,901 | 3,381 |

Each of the four positive groups lies individually within the central
10th--90th percentile interval of the benign flow-size distribution and the
benign packet-count distribution (100% for each marginal feature). This is a
range-overlap summary, not a multivariate classifier or an indistinguishability
claim.

The stream scan parsed 5,398 TCP flows in the 109 NonVPN captures. Four flows
contained the raw four-byte substring `FHAM`; all four were in `scp1.pcapng`.
No observed raw `FHAM` substring was followed by the version byte in the tested
five-byte signature, and there were no observed versioned `FHMS` markers.
Three other streams in `scp1.pcapng` hit the reassembler's 1-MB pending-buffer
cap and were resynchronized. The versioned-marker finding therefore describes
successfully reassembled regions, not all bytes discarded during cap-triggered
resynchronization.

## Interpretation and limits

TLS 1.3 hides the custom application marker from this TCP-payload scanner, as
expected for encrypted application data. This result says nothing about TLS
fingerprints, record-size patterns, timing analysis, endpoint metadata, or
classification by a trained adversary. The background consists of labeled
application sessions captured with unrelated applications closed; it is not
mixed ordinary traffic. The marginal percentile overlap cannot support a
claim that FHAM-positive flows blend into routine traffic. The study also does
not measure live deployments or message-conditioned cover selection.

These experiments extend the packet-local signature baseline with synthetic
positive flows and stream reassembly. They do not evaluate image-only
steganalysis, and they do not resolve exact message recovery after geometric
transformation: the separate geometry pilot still reports 0/40 exact recovery
from transformed pixels for the tested transformations.

## Reproduction and files

Run from the repository root on a machine with the extracted dataset in
`D:\dataset`:

```powershell
python scripts/traffic_transport_pilot.py --background D:\dataset --lengths 40 200 --trials-per-image 5
```

To rescan the background while reusing the synthetic positive PCAPs and their
protocol checks:

```powershell
python scripts/traffic_transport_pilot.py --background D:\dataset --lengths 40 200 --trials-per-image 5 --reuse-positive-captures
```

The script reads, but does not modify, external dataset captures. It writes
aggregate flow features and synthetic PCAPs only; source background packet
payloads and IP addresses are not copied into the published result tables.

- `scripts/traffic_transport_pilot.py` — generator and TCP stream analysis.
- `results/traffic_transport_pilot.csv` — four-row profile summary.
- `results/traffic_transport_protocol_checks.csv` — application-level checks.
- `results/traffic_transport_positive_flows.csv` — aggregate synthetic-flow features.
- `results/nonvpn_tcp_capture_flows.csv` — aggregate flow and resynchronization counts by capture.
- `results/traffic_transport_pcaps/` — two generated synthetic PCAP files.
