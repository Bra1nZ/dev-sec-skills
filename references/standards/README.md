# Standards Library

Local copies of freely available standards used to build the crosswalk.

Start with [`SOURCES.md`](SOURCES.md): it lists the source URL, license,
redistribution status, and SHA-256 of every downloaded file. Attribution
notices are in [`NOTICE.md`](NOTICE.md).

## What is here

- NIST SP 800-218 (SSDF), NIST SP 800-160 Vol. 1 Rev. 1, NIST SP 800-115.
- OWASP ASVS 5.0.0 (CC BY-SA 4.0).
- SARIF 2.1.0 (OASIS).
- CWE catalog XML.
- RFC 2119 and RFC 8174.
- SLSA specification source files.
- Diátaxis source pages.

## What is not here

- ISO/IEC standards: paywalled. Use the official ISO catalog and cite the
  version; do not copy full text.
- ФСТЭК 55/76/64 and ГОСТ Р 56939/71207: the user supplied local PDFs, but
  their redistribution terms are unclear. The crosswalk summarizes the
  engineering requirements; the full text stays outside the repository.
- Google and Microsoft style guides: link-only, copyrighted.

## Rules

1. Do not add a document without recording its source and license in
   `SOURCES.md`.
2. Do not replace a file silently. Update the hash and the date.
3. Do not present a downloaded standard as an audit or a certificate.
4. If a license requires attribution or share-alike, keep the notice with the
   file.

## Integrity

```bash
cd references/standards/downloaded
sha256sum -c <(grep -E '^\| `' ../SOURCES.md | sed -E 's/^\| `([^`]+)`.*`([0-9a-f]{64})`.*/\2  \1/')
```

If a hash fails, re-download from the recorded source and investigate before
updating anything.
