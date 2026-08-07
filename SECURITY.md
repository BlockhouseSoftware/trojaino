# Security Policy

AI Shield is an alpha deterministic scanner. It does not prove that scanned software is safe, complete a full security audit, or replace human review.

## Supported version

Security fixes are currently made only on the latest development version. No stable release line is supported yet.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or include secrets, live credentials, private source code, or third-party findings in a report.

Use GitHub's private vulnerability reporting flow for this repository when it is available: open the repository's **Security** tab, choose **Advisories**, and select **Report a vulnerability**. If that option is unavailable, contact a repository owner privately before sharing details.

Include the affected version or commit, a minimal reproduction, impact, and any suggested mitigation. Use inert placeholders in evidence. Maintainers will acknowledge the report and coordinate next steps; response times are not yet guaranteed during alpha.

## Scope and handling

- Reports about deterministic rule bypasses, unsafe evidence disclosure, path-boundary failures, and package or CLI behavior are in scope.
- Do not test against systems or repositories you do not own or lack permission to assess.
- AI Shield reports may contain sensitive paths or evidence. Review and redact them before sharing.