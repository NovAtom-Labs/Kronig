# Sentaurus Integration

## Current state

The local repository now contains a deterministic Sentaurus Device compiler, Ed25519-signed remote protocol, reference licensed-host service, strict native-result normalizer, and cross-backend conformance rules. The compiler can generate and inspect `sdevice.cmd` without a license. Real execution remains intentionally unconfigured on this machine.

The current compiler expects a reviewed `device.tdr` structure or mesh artifact at runtime. Producing or supplying that artifact for the exact Sentaurus release is the main licensed-machine integration item. No proprietary manual or licensed example belongs in this repository.

DEVSIM remains independent and runnable throughout this work.

## Stable switching boundary

The natural-language request, clarification flow, `ExperimentSpec`, capability check, plan approval, validation, evidence bundle, and report do not depend on either simulator. Backend-specific code is limited to the adapter, runner, normalizer, and capability manifest.

Switching backends means selecting a different binding for the same validated portable specification. It does not mean renaming files or assuming both simulators implement identical physics.

## What is implemented

- Fixed-template `sdevice.cmd` generation with no raw native syntax from users or models.
- Reviewed mappings for Fermi statistics, mobility, SRH, Auger, and Old Slotboom band-gap narrowing.
- Ohmic and explicit metal work-function contact rendering.
- Deterministic experiment, command, runtime, and compiler digests.
- Source mapping from command lines back to specification paths.
- Signed ZIP submission with exact version binding and five-minute validity.
- Replay prevention, digest verification, path traversal checks, archive limits, a flat input allowlist, and output allowlisting.
- One configured executable, argument arrays without a shell, wall-time limits, CPU limits, and memory limits.
- Strict JSON tabular normalization with SI conversion and non-finite-value rejection.
- Case-specific conformance outcomes: passed, warning, failed, or not applicable.

## Licensed-machine checklist

Do not change `execution_state` to `configured` until every item is recorded and reviewed:

1. Exact Sentaurus release and patch level.
2. Absolute `sdevice` executable path and executable hash.
3. The operating-system service account and file permissions.
4. A reviewed method for generating or supplying `device.tdr` from the portable region, contact, doping, and mesh data.
5. An authorized native-to-JSON extraction procedure for the allowlisted result fields.
6. Client Ed25519 public verification key installed on the runner.
7. HTTPS service identity, certificate policy, and network allowlist.
8. CPU, memory, wall-time, disk, upload, file-count, and concurrency quotas.
9. Exact output allowlist and retention period.
10. Restricted manual and example locations, license scope, allowed users, and version tags.
11. One domain-expert-reviewed golden run for each enabled conformance case.
12. A signed conformance report attached to the pilot release evidence.

## Runner configuration

The client signs submissions with its private key. The licensed runner stores only the matching trusted public key. Keys must be generated and distributed through the deployment secret process, never committed.

Client settings:

```text
TCAD_SENTAURUS_ENDPOINT=https://licensed-runner.example
TCAD_SENTAURUS_VERSION=<exact-release>
TCAD_SENTAURUS_SIGNING_PRIVATE_KEY=<base64-raw-ed25519-private-key>
TCAD_SENTAURUS_TRUSTED_PUBLIC_KEY=<base64-raw-runner-identity-key>
```

Licensed-host settings map to `SentaurusRunnerSettings`: job root, exact executable, exact version, trusted client public key, upload limit, execution timeout, file limit, and output allowlist. Keep the service disabled if any required value is absent.

The protocol exposes:

- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}/status`
- `GET /v1/jobs/{job_id}/result`

It never exposes a shell, model prompt, unrestricted file path, or user-controlled executable.

## One-day licensed-machine procedure

1. Install the current commit in an isolated Python 3.13 environment.
2. Record the exact release, executable hash, account, quotas, TLS identity, and retention policy.
3. Install the trusted client public key.
4. Review the generated `sdevice.cmd` snapshot against the authorized documentation for that release.
5. Complete the reviewed structure or mesh generation step and native JSON extraction step.
6. Run `examples/al-pn-al-equilibrium.yaml` manually once and compare it with the expert golden deck and plots.
7. Start the reference service behind the approved HTTPS identity.
8. Run `pytest -m sentaurus tests/integration/test_cross_backend_conformance.py -q` from the client.
9. Compare the hash-verified bundles with `tcad-agent conformance compare /path/to/devsim-bundle /path/to/sentaurus-bundle --case al-pn-al-equilibrium --output conformance-report.json`.
10. Review every failed or warning comparison. Do not loosen a tolerance without the TCAD domain lead approving the case file.
11. Attach both bundles and `conformance-report.json`, then mark the manifest configured.

## Rollback

If the version, license, signature, parser, structure input, validation, or conformance check fails, keep or return `execution_state` to `unconfigured`. Existing evidence bundles stay readable. DEVSIM continues through its separate adapter and runtime.
