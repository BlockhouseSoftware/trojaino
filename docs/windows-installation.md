# Install and verify Trojaino on Windows

**Trojaino: Local Trust Scanner**

**Your first line of defense.**

Trojaino is a local, deterministic scanner for AI-built or downloaded software—not a guarantee that any program is safe.

## Get an official release

Download Windows artifacts only from the [BlockhouseSoftware/trojaino Releases page](https://github.com/BlockhouseSoftware/trojaino/releases). An official Windows release contains a versioned installer named:

```text
Trojaino-Setup-<version>.exe
```

Release artifacts and checksums are published together. Do not rely on a filename, a reposted binary, or a similarly named PyPI package as proof of origin.

## Verify the download before installing

1. On the GitHub Release page, locate the SHA-256 checksum published for the exact installer version.
2. In PowerShell, calculate the checksum of the downloaded file:

   ```powershell
   Get-FileHash .\Trojaino-Setup-<version>.exe -Algorithm SHA256
   ```

3. Compare the output with the checksum published on that same official release page. They must match exactly. If they do not match, **do not run the installer**.

A matching checksum proves that the file you downloaded matches the release artifact named by that release page; it does not prove that the software is safe or appropriate for every environment.

## Verify the publisher signature

The intended verified publisher for signed Trojaino releases is **Blockhouse Software**. Signed releases are produced after the protected release-signing workflow has completed; an unsigned preview artifact is not a publisher-verified release.

In PowerShell, inspect the installer signature:

```powershell
$sig = Get-AuthenticodeSignature .\Trojaino-Setup-<version>.exe
$sig.Status
$sig.SignerCertificate.Subject
```

For a signed official release, verify both conditions:

- `Status` is `Valid`.
- The certificate subject identifies `Blockhouse Software` as the publisher.

To inspect timestamp information, use the Windows file properties **Digital Signatures** tab or your organization’s certificate-inspection tooling. A valid timestamp matters because it preserves signature validity after the signing certificate is renewed or expires.

If the signature is absent, invalid, or identifies a different publisher, stop and obtain the artifact again from the official release page. Do not bypass a signature warning merely to continue installation.

## SmartScreen guidance

Windows SmartScreen reputation and publisher verification are separate controls. A newly signed application can still receive an initial reputation warning while it establishes distribution history.

- If the checksum, release provenance, or publisher identity is wrong or unclear, **do not run the installer**.
- If they all verify but your organization’s policy still blocks it, use the documented internal security-review process or contact Blockhouse Software; do not treat a warning as something to click through blindly.

## Install

1. Run `Trojaino-Setup-<version>.exe` from the verified download.
2. The installer is per-user and installs Trojaino under your local application-data directory. It does not require Python, pip, or administrator elevation.
3. Open a **new** PowerShell or Command Prompt window so Windows reads the updated user `PATH`.
4. Confirm the command is available:

   ```powershell
   tjscan --help
   ```

   Double-clicking `tjscan.exe` in the Trojaino installation folder opens the
   desktop scanner. Running `tjscan` with an argument in PowerShell or Command
   Prompt continues to use the command-line interface.

5. Scan a project before installing, running, or deploying it:

   ```powershell
   tjscan scan C:\path\to\project
   tjscan scan C:\path\to\project --html C:\path\to\report.html
   ```

Exit codes are intended for automation:

- `0` — `NO CRITICAL RISKS FOUND`
- `1` — `CAUTION`
- `2` — `DO NOT RUN`

`NO CRITICAL RISKS FOUND` means Trojaino’s current deterministic checks did not identify a critical risk. It is not a safety guarantee.

## Uninstall

Use **Installed apps** in Windows Settings and select Trojaino, or run the uninstaller from the Trojaino install directory. Uninstall removes the installed program and its Trojaino `PATH` entry. Reports you wrote outside the installation directory are not removed.

## Scope: one layer, not the whole program

Trojaino is a free local scanner focused on evidence before execution. Use it alongside human review and the controls appropriate to your environment. Continuous monitoring, web scans, and broader system coverage are complementary paid or organizational security layers—not claims that Trojaino replaces them.

For source-checkout and development installation, see the repository [README](../README.md).
