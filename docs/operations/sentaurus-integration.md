# Sentaurus Integration

## Current state

The repository contains a deterministic candidate Sentaurus Device compiler,
an SSH/SFTP bridge, a separate signed-HTTP reference protocol, exported-table
normalization and cross-backend conformance rules. Compilation and synthetic
interoperability tests do not need a license. Real execution remains unqualified
and unconfigured on this machine. A reviewed compiler snapshot is not a native
syntax or physics benchmark.

The current compiler expects a reviewed `device.tdr` structure or mesh artifact at runtime. Producing or supplying that artifact for the exact Sentaurus release is the main licensed-machine integration item. No proprietary manual or licensed example belongs in this repository.

DEVSIM remains independent and runnable throughout this work.

## SSH development branch

The `feature/ssh-remote-tcad` branch also contains an SSH/SFTP execution bridge.
It keeps the application local and does not require the HTTPS service or a modern
Python installation on the remote host. It is not yet a generic remote agentic
workspace. Remote repository browsing/editing, managed interactive jobs, scheduler
support, verified cancellation and native result export remain development work.

The bridge uses `TCAD_SENTAURUS_RUNNER=ssh`, `TCAD_HPSC_HOST`, `TCAD_HPSC_USER`,
optional `TCAD_HPSC_PORT` and `TCAD_HPSC_REMOTE_ROOT`. It loads the current user's
known-host keys and rejects unknown or changed server keys. Before using Kronig,
verify the server fingerprint with the HPC administrator and establish the correct
known-host entry through your normal authorized SSH login. Do not disable host-key
checking or trust an unverified `ssh-keyscan` result.

Existing SSH agent/default identity keys are supported. An explicitly supplied
`TCAD_HPSC_PASSWORD` is accepted for compatibility but is never collected through
an invisible terminal or written back into the process environment. No password is
required when key authentication is available. Do not put credentials in tracked
files. SSH-config aliases, ProxyJump and interactive MFA are not implemented by
this Paramiko bridge; successful command-line SSH alone does not qualify them.

The bridge does not generate a missing mesh, decode arbitrary TDR binaries, bypass
license checks or prove that a disconnected remote process has stopped. Its
presence does not mark Sentaurus configured or scientifically qualified.

## Stable switching boundary

The natural-language request, clarification flow, `ExperimentSpec`, capability check, plan approval, validation, evidence bundle, and report do not depend on either simulator. Backend-specific code is limited to the adapter, runner, normalizer, and capability manifest.

Switching backends means selecting a different binding for the same validated portable specification. It does not mean renaming files or assuming both simulators implement identical physics.

## What is implemented

- Fixed-template `sdevice.cmd` generation with no raw native syntax from users or models.
- Candidate mappings for Fermi statistics, mobility, SRH, Auger, and Old Slotboom band-gap narrowing. Native model selection and parameters need release-specific qualification.
- Ohmic and explicit Schottky metal-work-function contact rendering, selected equations, scalar temperature, and contact voltage offsets.
- Region-count-independent compilation, up to the declared 32-region limit. The external mesh must implement the exact geometry, profiles and contact names.
- Equilibrium, DC sweeps and explicit DC-point schedules. Decreasing sweeps, nonzero starts and contact offsets are retained. Each target has its own normalized-time continuation and snapshot prefix. Internal continuation steps are not additional researcher-requested samples.
- Explicit refusal of unmapped physics parameters, spatial temperatures, interface charge, Richardson overrides, adaptive-recovery controls, profile sampling and numerical overrides. No parameter is dropped to make a deck compile.
- Immutable mesh attachment with exact release/review references and per-file/whole-bundle hash checks before SSH connects. This verifies identity and completeness, not opaque mesh contents.
- Deterministic experiment, command, runtime, and compiler digests.
- Source mapping from command lines back to specification paths.
- Signed ZIP submission with exact version binding and five-minute validity.
- Replay prevention, digest verification, path traversal checks, archive limits, a flat input allowlist, and output allowlisting.
- One configured executable, argument arrays without a shell, wall-time limits, CPU limits, and memory limits.
- Legacy JSON and version-2 JSON/CSV exported-table normalization, with quantity-specific SI units, bias-profile families, complex frequency responses, absolute versus per-area quantities, finite-value checks, masks for failed points and source hashes.
- Bounded, flat, hash-checked CSV references. SSH fetches only validated export references and rejects non-regular or oversized tables. Missing native exports, mismatched releases and mismatched export provenance cannot become a successful results view.
- Case-specific conformance outcomes: passed, warning, failed, or not applicable.

### Preparing a native mesh bundle

The Python interface is intentionally explicit until native mesh generation has
been qualified. This is an engineering setup operation, not a researcher prompt:

```python
from pathlib import Path
from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.adapters.sentaurus.runtime import bind_mesh, validate_bundle

adapter = SentaurusAdapter.from_defaults()
candidate = adapter.compile(spec, Path("candidate-job"))
prepared = bind_mesh(
    candidate,
    Path("reviewed-device.tdr"),
    Path("prepared-job"),
    simulator_version="<exact installed release and patch>",
    review_reference="<your mesh and deck review record>",
)
validate_bundle(prepared)
```

Both destination directories must be new. `bind_mesh` copies the original inputs
and the supplied mesh into a new bundle. It cannot inspect or prove geometry,
doping, material or contact correctness inside a proprietary binary. The review
must cover all of those, the selected models and defaults, the deck, dimensions,
area/current normalization and the exact installed release. A review reference is
not a scientific benchmark or permission to bypass HPC policies.

Generated jobs without their mesh or review fail before SSH connection. The
low-level bridge retains compatibility with older manually constructed jobs
without an adapter manifest; those are not qualified adapter jobs. The separate
HTTP service keeps its existing restricted archive/output protocol and is not the
deployment path for the new CSV export workflow.

### Export contract and scientific results

`sentaurus-result.json` version 1 remains readable. Version 2 is a strict export
manifest, not a renamed TDR binary. The authorized native exporter must produce:

- `schema_version: "2.0"`, actual `simulator_version`, `status: "completed"` and unique `terminals`.
- `provenance`: `compiler_version`, `experiment_sha256` and `mesh_sha256`, copied from the submitted job manifest. The importer preserves these as declared provenance; the SSH bridge compares them with the submitted bundle.
- Explicit `sign_convention`: terminal current positive into the device; terminal charge outward displacement flux. Do not relabel a simulator convention without converting the values.
- `axes`: keyed axes with `id`, `kind`, `label`, native `unit` and finite `values`.
- `datasets`: keyed entries with matching `id`, physical `quantity`, `label`, `unit`, `axes`, `shape`, and `centering`. Flatten multidimensional values in row-major order. Use inline `values` and optional `imaginary_values`, or a `table` containing a flat CSV `file`, its `sha256`, `column` and optional `imaginary_column`. CSV files have one header and numeric rows, without empty cells or duplicate headers.
- `operating_points`: ordered zero-based `index`, `state`, SI `coordinates`, optional SI terminal-current-density/component and charge-density maps, attempts and diagnostic message. Failed/skipped points remain failures and are masked in plots. Coordinates should use the matching axis IDs, for example `bias` in V, `time` in s or `frequency` in Hz. The importer never converts an unknown point state into convergence.

Examples of physical quantities: `potential` in V, `electron_density` in cm^-3 or
m^-3, `terminal_current_density` in A/cm^2 or A/m^2,
`absolute_terminal_current` in A, `capacitance_density` in F/cm^2 or F/m^2,
`capacitance` in F, `admittance` in S and `admittance_density` in S/m^2.
Absolute quantities and densities are never interconverted without geometry.
Spatial coordinates may be m, cm, um or nm; operating-point SI maps must already
be in their declared SI units. Recombination uses m^-3*s^-1 or cm^-3*s^-1.

Spatial profiles can use independent position axes, or `[bias, position]` families
on one shared grid. Complex curves retain real and imaginary values. Different
mesh grids must use separate datasets rather than pretending they share positions.
Do not stitch discontinuous interface values into a single continuous profile.
The shared workbench can select a profile point and zoom without opening HTML in
an external browser. Importing capacitance or AC data does not enable native AC
simulation: that compiler path is still unsupported.

Limits: 64 MiB per export/CSV file, 64 MiB total fetched CSV bytes, 256 datasets,
64 axes, 10,000 operating points and 4,000,000 values per dataset. Invalid data
fails normalization. The LLM does not guess units, parse binary TDR or fill gaps.

### Offline verification

```sh
python -m pytest tests/unit/adapters/test_sentaurus*.py tests/unit/runners/test_ssh_audit.py -q
python -m pytest tests/unit/web/test_headless_research_dom.py -q
```

The pipeline fixtures deliberately use an opaque fake mesh and a synthetic solver
over local filesystem/process transport. They cover compile, preparation,
upload/execution/download, SI conversion and workbench queries, plus nonzero exit,
timeout, missing export, stale data and wrong-release paths. On POSIX hosts without
GNU `timeout`, the tests use a clearly labeled test-only deadline substitute.
They do not exercise SSH authentication, HPC queues, Sentaurus parsing, license
checkout, native binary export, numerical convergence or physical accuracy.

## Licensed-machine checklist

Do not change `execution_state` to `configured` until every item is recorded and reviewed:

1. Exact Sentaurus release and patch level.
2. Absolute `sdevice` executable path and executable hash.
3. The operating-system service account and file permissions.
4. A reviewed method for generating or supplying `device.tdr` from the portable region, contact, doping, and mesh data.
5. An authorized native-to-JSON extraction procedure for the allowlisted result fields.
6. Authorized SSH account, verified host key and network access for SSH deployments; no local runtime installation on the HPC is required by this bridge.
7. For the optional HTTP service only: client Ed25519 public verification key, HTTPS service identity, certificate policy and network allowlist.
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

## Licensed-machine integration procedure

This is not a promise that all qualification can be finished in one day.

1. Keep Kronig and its modern Python runtime on the user's workstation. The SSH path uses existing SSH/SFTP, a POSIX shell, GNU `timeout` and the already installed licensed vendor executables on the HPC. It does not install Python, Kronig or an HTTP service there.
2. Record the exact vendor release, executable hashes, account, scheduler rules, quotas, permitted commands, license policy and retention policy. Do not run compute-heavy jobs on a login node if the site requires a queue.
3. Verify host fingerprints through the administrator, establish authorized authentication, and test small upload/read/write/download operations only within the allocated job directory.
4. Review the generated `sdevice.cmd` against authorized release-specific documentation. Qualify a true 1D native mesh builder against geometry, contacts, doping and interfaces. Do not silently extrude a 1D request into 2D.
5. Implement and verify the native exporter using installed vendor tools. It must extract units, terminal conventions, operating-point identity, convergence and native model evidence into the strict export contract. The present bridge does not yet invoke this exporter automatically.
6. Supply and hash-bind a reviewed mesh for the first controlled native run. A direct `sdevice` exit without the required export is deliberately reported as malformed results, not success.
7. Run domain-expert-reviewed reference cases for every proposed enabled capability and include grid convergence, units, contact physics, current/charge conservation and requested outputs. Native syntax acceptance alone is not a physics benchmark.
8. Compare the hash-verified bundles using `tcad-agent conformance compare /path/to/devsim-bundle /path/to/sentaurus-bundle --case al-pn-al-equilibrium --output conformance-report.json`, with case-appropriate evidence and approved tolerances. The existing environment-gated live conformance test remains a qualification placeholder, not an implemented automatic SSH qualification harness.
9. Verify scheduler submission, monitoring, reconnect behavior, cancellation/reaping, output quotas and failure diagnostics against site policy before unattended production use.
10. Attach the evidence and reviewed conformance report before marking the backend configured. No tolerance should be loosened merely to enable a capability.

The optional signed-HTTP reference service has a separate deployment procedure
and requires an approved modern host environment, keys and HTTPS identity. It is
not required for, or a workaround around restrictions on, the SSH deployment.

## Rollback

If the version, license, signature, parser, structure input, validation, or conformance check fails, keep or return `execution_state` to `unconfigured`. Existing evidence bundles stay readable. DEVSIM continues through its separate adapter and runtime.
