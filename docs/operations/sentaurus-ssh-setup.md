# Run Sentaurus from Kronig over SSH

This guide connects a Kronig installation on **any computer** (Windows, macOS or Linux) to a
Sentaurus TCAD installation on an HPC cluster. After setup, you ask for a simulation in plain
English, Kronig plans it, runs it on the HPC, and shows the results like any other run.
DEVSIM keeps working exactly as before. Both simulators are always available; you pick one per
request.

## What you need

On your computer:

- Kronig installed and working (see [INSTALLATION.md](../../INSTALLATION.md)).
- Network access to the HPC. If the HPC is only reachable from a campus network or VPN, join it
  first (Tailscale, a university VPN, and so on). Kronig does not do this for you.
- A login (user name plus password or SSH key) for the HPC.

On the HPC (nothing needs to be installed by you):

- Sentaurus with the programs `sde` and `sdevice`, and permission to use its licenses.
- A normal Linux shell and the `timeout` command (almost every cluster has both).

Nothing else is needed there. No Python, no conda, no Kronig.

## Step 1. Collect three facts

| Fact | Example | How to find it |
| --- | --- | --- |
| HPC address | `10.20.30.40` or `hpc.example.edu` | Ask your HPC administrator or look at the command you normally use: `ssh USER@ADDRESS`. |
| Your user name | `jsmith` | The `USER` in that same command. |
| Sentaurus release | `O-2018.06-SP2` | Log in with SSH and run `sdevice -h`. The banner says `Version O-2018.06-SP2`. Copy that text exactly. |

## Step 2. Fill in the `.env` file

In the Kronig folder, copy `.env.example` to `.env` if you have not already (`.env` is ignored by
git, so your password never gets committed). Then set these lines:

```text
TCAD_SENTAURUS_RUNNER=ssh
TCAD_HPSC_HOST=<HPC address from step 1>
TCAD_HPSC_USER=<your user name>
TCAD_HPSC_PASSWORD=<your password, or leave empty if you use an SSH key>
TCAD_SENTAURUS_VERSION=<release from step 1>
```

Everything else in that section already has a sensible default. The comments in `.env.example`
explain each line.

## Step 3. Check the connection

Open a terminal in the Kronig folder and run:

```text
# Windows
.\.venv\Scripts\tcad-agent.exe sentaurus-check

# macOS / Linux
.venv/bin/tcad-agent sentaurus-check
```

It prints one line per check, `ok` or `FAIL`, and says how to fix a failure. It stops at the
first failure that blocks the rest.

| Check | If it fails |
| --- | --- |
| `settings` | A line from step 2 is missing in `.env`. The message names it. |
| `network` | Your computer cannot reach the HPC. Join its network or VPN, then rerun. |
| `host key` | First time on this computer. Ask the HPC administrator to confirm the fingerprint shown, then rerun with `--trust-host`. Kronig refuses unknown servers on purpose. |
| `login` | Wrong user name or password. Fix `TCAD_HPSC_USER` or `TCAD_HPSC_PASSWORD`, or load an SSH key. |
| `tools` | `sde` or `sdevice` was not found on the HPC. See step 4. |
| `release` | The HPC runs a different Sentaurus release than `TCAD_SENTAURUS_VERSION`. Use the version it prints. |
| `work folder` | Kronig cannot write its job folder. Set `TCAD_HPSC_REMOTE_ROOT` to a folder you can write to. |

For a last, slower proof that your account can use the licenses, run it with `--deep`. It starts
the Sentaurus structure editor on the HPC and checks that it finishes.

## Step 4. Only if the tools were not found

Many clusters hide software behind a "load" command. Pick one option and put it in `.env`:

```text
# The cluster uses environment modules:
TCAD_SENTAURUS_SETUP=module load sentaurus

# The cluster has a setup script:
TCAD_SENTAURUS_SETUP=. /opt/synopsys/setup.sh

# You know the folder that holds the sde and sdevice programs:
TCAD_SENTAURUS_BIN=/opt/synopsys/sentaurus/bin

# The licenses are not already configured for your login:
TCAD_SENTAURUS_LICENSE=27020@licenses.example.edu
```

To find the right answer, log in and try `module avail`, or `which sdevice`, or ask your
administrator. `TCAD_SENTAURUS_SETUP` must be one line. It runs on the HPC under your own login,
so only put commands in it that you would type there yourself. Rerun the check afterwards.

## Prefer clicking? Use the desktop Settings

In the desktop app, open **Settings** and scroll to **Sentaurus on a remote HPC**. The fields are the same
settings as the `.env` file above:

| Field | Setting it writes |
| --- | --- |
| HPC address, SSH port, login name | `TCAD_HPSC_HOST`, `TCAD_HPSC_PORT`, `TCAD_HPSC_USER` |
| Sentaurus release | `TCAD_SENTAURUS_VERSION` |
| HPC password | `TCAD_HPSC_PASSWORD` (kept in the operating system's protected storage, never in a plain file; leave it empty to use an SSH key) |
| Advanced: remote work folder, setup command, bin folder, license server | `TCAD_HPSC_REMOTE_ROOT`, `TCAD_SENTAURUS_SETUP`, `TCAD_SENTAURUS_BIN`, `TCAD_SENTAURUS_LICENSE` |
| Advanced: more environment variables | any other `TCAD_` setting, one `NAME=value` per line |

Saving restarts Kronig's private service. Then press **Test connection**: it runs the same checks as
`tcad-agent sentaurus-check` and lists each one with what to fix. **Test with license check** also starts the
structure editor to prove a license is available. If the server's key is not trusted yet, the test shows its
fingerprint and offers **Trust this host key**. Confirm that fingerprint with your HPC administrator first.

## Choosing DEVSIM or Sentaurus

Above the message box there is a **Simulator** switch. It applies to the next request, needs no restart, and is
remembered. Saying "use Sentaurus" or "use DEVSIM" in a request always wins over the switch. If Sentaurus is not set
up yet, clicking it explains what is missing and opens Settings.
## Step 5. Use it

Start Kronig as usual. Name the simulator in your request:

- "Use Sentaurus to simulate a PN junction under forward bias and plot the I-V."
- "Use DEVSIM to ..." or no simulator at all runs DEVSIM.

To make Sentaurus the default when a request names no simulator, set `TCAD_BACKEND=sentaurus`.
Kronig asks the usual clarifying questions, shows the plan for approval, uploads the job, runs
it on the HPC, downloads the results and displays them. Every SSH action is written to an audit
log inside the run's evidence bundle (`logs/ssh-audit.json`).

## What it can do today

- Silicon structures with uniform doping, ohmic and metal-work-function contacts.
- Equilibrium and DC voltage studies, with terminal current and charge, potential, field,
  carrier densities, band edges, quasi-Fermi levels, mobility and recombination.
- One-dimensional requests are built as a unit-height two-dimensional slab. Kronig checks that the
  result stays uniform across the slab and refuses the run if it does not.

Not available yet: oxide or MOS structures, 2D devices such as MOSFETs, AC and transient studies,
and non-uniform doping. These runs have not been validated against measurements. Kronig asks
before changing anything you requested, and refuses what it cannot do.

## If a run fails

The result message names the stage that failed:

| Message starts with | Meaning and fix |
| --- | --- |
| `Sentaurus tools were not found` | Step 4. |
| `structure editor failed` | The geometry or mesh could not be built. The message quotes Sentaurus. |
| `device simulation failed` | The solver stopped. The message quotes Sentaurus, often a convergence problem. |
| `timed out` | The run exceeded its time budget. Use fewer bias points or a coarser mesh. |

Raw Sentaurus logs are saved next to the results (`sde.stdout.log`, `sdevice.stdout.log`).

## Moving to a different HPC

Change only the `.env` lines for the new HPC (address, user, password, release, and the tool
setup in step 4), join its network, and rerun the check. Nothing else in Kronig changes.
