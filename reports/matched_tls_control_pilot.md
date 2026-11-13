# Matched TLS 1.3 record-size control

## Question

Does FHAM's application content create a distinct TLS record-size pattern when
compared with an ordinary application exchange using the same TLS stack and
the same plaintext request and response lengths?

## Method

We generated 80 FHAM exchanges: eight controlled covers, five messages per
cover, at each of 40 and 200 characters. For each FHAM exchange, the control
uses a syntactically valid HTTP/1.1 JSON request and response with exactly the
same respective plaintext byte lengths. The FHAM and HTTP exchange each use a
separate TLS 1.3 session from the same local OpenSSL configuration, with the
same pinned test certificate. Each request and response is submitted as one
application write. We parsed actual TLS records emitted by Python's
`ssl.MemoryBIO` and compared their directions, counts, and wire lengths.

This method does not use sockets, capture TCP segments, or evaluate endpoint
metadata, TLS client fingerprints, or real network timing. It measures TLS
record framing from an actual TLS implementation under controlled matched
plaintext lengths.

## Results

| Message length | FHAM request bytes | Matched HTTP request bytes | FHAM reply bytes | Matched HTTP reply bytes | TLS records per exchange | Client TLS bytes, FHAM/HTTP | Server TLS bytes, FHAM/HTTP | Exact directional record-length match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 40 characters | 368 | 368 | 149 | 149 | 13 | 720 / 720 | 2,021 / 2,021 | 40/40 pairs |
| 200 characters | 1,008 | 1,008 | 149 | 149 | 13 | 1,360 / 1,360 | 2,021 / 2,021 | 40/40 pairs |

Across all 80 pairs, the complete client-direction and server-direction TLS
record-length sequences matched exactly. The byte string `FHAM\x01` was
absent from every encrypted FHAM and HTTP TLS byte stream.

The TLS content is therefore concealed from this marker scan, and matched
plaintext lengths produce the same observable record-size sequence in this
test. The message length remains visible through total traffic volume: the
client-direction TLS bytes increase from 720 to 1,360 between the 40- and
200-character conditions. This pilot provides no evidence that the resulting
flows are indistinguishable from ordinary network traffic; the HTTP controls
are deliberately matched by size and generated with the same TLS stack.

## Reproduction

```powershell
python scripts/matched_tls_control_pilot.py
```

The script writes `results/matched_tls_control_pilot.csv`. It reuses the
authenticated FHAM application-exchange implementation and the existing
controlled cover/message corpus; it does not read or write the external PCAP
dataset.
