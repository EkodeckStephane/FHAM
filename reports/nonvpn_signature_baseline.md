# Non-VPN packet-capture signature baseline

## Dataset and procedure

The analysis used the 109 extracted PCAP/PCAPNG files in the three `NonVPN-PCAPs` archives under `D:\dataset`. The captures contain labeled application sessions from the ISCX VPN-nonVPN 2016 dataset. The dataset documentation describes targeted sessions in which unrelated applications were closed during capture; this is a labeled non-VPN baseline, not a mixed, continuously observed enterprise trace. See the [UNB dataset page](https://www.unb.ca/cic/datasets/vpn.html) and Draper-Gil et al. (2016), DOI `10.5220/0005740704070414`.

The in-repository parser read all 109 packet files from D: and wrote only aggregate results to `results/nonvpn_trace_baseline.csv`. It decoded TCP/UDP payloads and searched packet-local payload bytes for `FHMS`, `FHME`, and `FHMT`. A second pass recorded marker, packet index, payload offset, and the single byte after the marker; it did not preserve surrounding packet content. No TCP stream reassembly or classifier training was performed.

## Results

- 109 captures and 21,919,108 packets were parsed; the packet-level wire-byte total was 24,613,957,972 bytes.
- The parser recorded 30 packet-marker hits for `FHMS`, 8 for `FHME`, and 7 for `FHMT`, across 9 of 109 captures.
- None of the 30 `FHMS` hits was followed immediately by version byte `01`; hence there were 0 packet-local occurrences of the current five-byte signature `FHMS 01`.
- All 30 `FHMS` matches occurred at nonzero offsets within packet payloads. They were substrings of the observed application traffic, not packet-start records.

## Interpretation and scope

The four-byte magic alone is not unique in this background corpus and should not be treated as a reliable detector for a valid FHAM session envelope. Adding the protocol version eliminated the observed packet-local `FHMS` candidates in this corpus. This is a baseline signature-collision result, not a sensitivity, ROC, or false-positive estimate for a deployed FHAM protocol: the captures contain no labeled FHAM-positive sessions, and packet-local scanning can miss markers split across TCP segments. The experiment does not measure flow size/timing detection, traffic batching, or FHAM encapsulated within TLS. Those properties remain unmeasured.

## Reproducibility files

- Parser: `scripts/analyze_nonvpn_traces.py`
- Per-capture aggregate: `results/nonvpn_trace_baseline.csv`
- Marker-only packet metadata: `results/nonvpn_marker_occurrences.csv`
- Input data: externally obtained ISCXVPN2016 non-VPN PCAP/PCAPNG files under `D:\dataset`; the PCAP files are not included in this repository.
