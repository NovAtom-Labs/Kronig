# DEVSIM Operations

## Supported runtime

- Python: 3.13
- DEVSIM package: 2.9.1
- default desktop executable: the absolute sibling `../devsim/.venv/bin/python`, or `../devsim/.venv/Scripts/python.exe` on Windows
- reviewed source commit: `43b41ca845184c47e22b72d144db7e7db8509377`

DEVSIM has its own virtual environment so product dependencies and simulator dependencies cannot silently alter each other.

The [source bootstrap](../../INSTALLATION.md) prepares this isolated runtime. If the simulator is elsewhere, set `TCAD_DEVSIM_PYTHON` to its absolute executable path. No DEVSIM version upgrade is needed for the current adapter expansion.

`requirements/devsim.txt` owns simulator pip dependencies across platforms. Its MKL requirement is selected only on Windows. Linux uses system OpenBLAS; macOS uses native math libraries. The application list supplies the shared NumPy constraint. Native setup checks and OS-specific prerequisites are in [Installation](../../INSTALLATION.md#dependency-ownership-by-operating-system).

On Windows the desktop launcher locates the pinned MKL runtime inside the simulator environment. For direct diagnostic CLI use, set `TCAD_DEVSIM_PYTHON` to the absolute simulator Python, set `DEVSIM_MATH_LIBS` to its `Library\bin\mkl_rt.dll` or `mkl_rt.*.dll`, and prepend that `Library\bin` directory to the process `PATH`. These are process-local environment values, not files to copy between machines.

## Internal validation wrapper

DEVSIM remains the complete local test backend while Sentaurus is being connected. Every ordinary code change must keep the DEVSIM end-to-end tests green.

Researchers normally run DEVSIM through the native workspace agent. The commands below are an
internal compatibility and diagnostic surface. The `run` command delegates to the same
`ExperimentEngine` as the desktop agent and does not implement a second workflow.

```bash
.venv/bin/tcad-agent validate examples/pn-junction.yaml

.venv/bin/tcad-agent compile examples/pn-junction.yaml \
  --backend devsim \
  --output compiled

.venv/bin/tcad-agent run examples/pn-junction.yaml \
  --backend devsim \
  --approve \
  --timeout-seconds 120 \
  --output runs
```

An older explicit approximation remains available as a fixture:

```bash
.venv/bin/tcad-agent run examples/al-pn-al-equilibrium-devsim.yaml \
  --backend devsim \
  --approve \
  --output runs
```

That fixture deliberately selects ohmic contacts, Boltzmann statistics, constant mobility and SRH. It is not the current capability boundary and must not be silently substituted for a researcher's requested physics. Current reviewed 1D paths include work-function Schottky boundaries, Fermi transport, Klaassen mobility, Auger, Slotboom band-gap narrowing, interface charge and canonical band/quasi-Fermi extraction. Equilibrium/DC support does not imply every dynamic combination is accepted. The capability manifest rejects unsupported combinations before execution. See the [capabilities and limitations](../../README.md#current-capabilities) and [Fermi/Klaassen verification](../verification/2026-10-14-fermi-klaassen-convergence.md).

Validation is safe and read-only. Compilation writes deterministic inputs but does not start the simulator. Run requires `--approve` and writes a new immutable bundle. Reusing a run ID is rejected by the bundle writer.

## Inspect a run

The CLI prints the final bundle directory. Check `manifest.json` first. A usable result requires:

- bundle `state` is `completed`
- native and canonical statuses are completed
- validation `overall` is `passed`
- simulator, compiler, input, and runtime identities are present
- every artifact hash matches its file

Print the report with:

```bash
.venv/bin/tcad-agent report runs/<run-id>
```

One-dimensional outputs retain density units unless physical area is explicitly supplied. The engine does not invent cross-sectional area to manufacture an absolute current or capacitance. Display-unit conversions come from canonical quantities, not report prose.
Multi-point DC studies retain a bias axis for terminal responses and every requested spatial
observable. The final single profile remains available for backward compatibility, while the
axis-aware datasets drive operating-point selection, profile comparison, and failed-point gaps.

## Build and query local knowledge

```bash
.venv/bin/python scripts/rebuild_knowledge_index.py --project-root . --fetch-sources --if-stale

.venv/bin/tcad-agent knowledge search "ohmic drift diffusion contact" \
  --backend devsim \
  --version 2.9.1
```

The rebuild script resolves authorized product guides from this repository and the separately
pinned public DEVSIM source and documentation checkouts from the parent NovAtom Labs directory.
It fetches missing reviewed public revisions without resetting existing work, builds a staged index and atomically replaces the generated index only after ingestion succeeds. An unchanged healthy index is reused. The index directory is ignored by Git and packaged separately for releases. Proprietary Sentaurus sources are not fetched or committed.

## Failure handling

- `invalid specification`: correct schema, units, topology, or references before capability checking.
- `backend_unsupported`: do not weaken physics silently. Return the exact unsupported field.
- timeout or nonconvergence: preserve the failed evidence, then use one bounded numerical recovery such as smaller voltage steps or equilibrium restart.
- failed physical validation: mark the scientific result as needing review even if DEVSIM returned exit code zero. A completed execution is not necessarily a trusted result. Preserve failed checks and evidence; never relabel them as passed.
- malformed native result: preserve stdout and stderr and fix the deterministic parser or compiler. Do not extract values from prose.

## Verification

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/pytest -q
```

Integration tests invoke the separately installed DEVSIM runtime. Unit tests remain simulator-independent.
Run `.venv/bin/mypy --strict src` separately as a static audit; current main has existing typing errors. See [Contributing](../../CONTRIBUTING.md) for the complete verification policy.
