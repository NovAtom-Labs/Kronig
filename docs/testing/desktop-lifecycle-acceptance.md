# Desktop Lifecycle Acceptance

The native shell owns the authenticated local backend and its process tree.

Verified automated cases cover idle quit, active-work refusal, explicit quit after cleanup failure,
window-close coordination, backend readiness failure, unresponsive graceful shutdown, forced process
termination, updater restart checks, and repeated close requests. Internal session deletion removes
run-owned approvals, grants, baselines, manifests, prompt preparations, prepared plans, and experiment
result records before deleting the parent run.

The development smoke launch starts the current source through `scripts/run_desktop_dev.py`. Native
package qualification for Linux, Windows, Intel macOS, and Apple Silicon remains a release-pipeline
responsibility and is not inferred from one host.
