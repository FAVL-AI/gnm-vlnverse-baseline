# H8 G2A — Trust-envelope fixture corpus

Static, committed, deterministic fixtures for the canonical trust-envelope schema and JCS (RFC 8785)
canonicalisation. Consumed by `tests/gnm/test_h8_trust_envelope.py`. **Fixture-only** — nothing here is a
real key, certificate, signature or trusted timestamp, and none of it can authorise protected use.

## Layout

- `canonical_vectors.json` — cross-language canonicalisation interop vectors. Each entry has
  `input_json` (the source), `canonical_utf8_hex` (the exact JCS canonical bytes, hex-encoded) and
  `canonical_sha256`. An independent implementation in any language canonicalises `input_json` and must
  reproduce `canonical_utf8_hex` byte-for-byte. Scheme = `JCS/RFC8785`; floats prohibited; strings must be
  NFC; object keys sorted by UTF-16 code units.
- `envelope_vectors/positive/*.json` — full valid envelopes. Expected `canonical_digest` is pinned in the
  catalogue as a drift/regression anchor.
- `envelope_vectors/negative/*.json` and `*.raw` — invalid inputs, one per structural failure mode. `.raw`
  files carry bytes that a normal serializer cannot emit (duplicate keys, float literals, `NaN`/`Infinity`,
  a UTF-8 BOM, a non-object root, a non-NFC string).
- `envelope_vectors/catalogue.json` — the manifest: for each vector, `file`, `purpose`,
  `expected_document_conformant`, `expected_reason_code`, and (positives) `expected_canonical_digest`.

## Invariants asserted by the corpus

- Every positive vector is `document_conformant=true`, `reason_code=TRUST_OK`, and reproduces its pinned
  canonical digest.
- Every negative vector is `document_conformant=false` with the exact `TRUST_*` reason code.
- A schema-valid envelope is still `signature_verified=false`, `not_revoked="unverified"`,
  `preflight_eligible=false`, `runtime_eligible=false`, `capture_eligible=false`. Schema conformance is
  never trust acceptance.

## Regeneration

The generator is intentionally not committed; the fixtures are static golden data. To regenerate/verify,
build envelopes per `scripts/gnm/h8_trust_envelope.py` (`build_valid()` mirror lives in the test module) and
recompute canonical bytes via `canonicalise_envelope` / `compute_envelope_digest`. Any change to the
canonicalisation rules will change the pinned hex/digests and fail these tests — that is the point.
