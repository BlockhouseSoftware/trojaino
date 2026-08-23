## Summary

-

## Verification

- [ ] Added or updated synthetic, no-secret fixtures where behavior changed
- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 -m trojaino scan . --profile release --json` (record verdict and exit code)
- [ ] `git diff --check`

## Risk and compatibility

- Verdict/disposition impact:
- False-positive/false-negative risk:
- Python/platform impact:

## Data hygiene

- [ ] No secrets, private source, unredacted third-party findings, pitch material, or internal operational documents are included
- [ ] The change does not claim that Trojaino or scanned software is safe, secure, or certified