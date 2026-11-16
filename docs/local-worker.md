# Run the local Python worker

The M1 Worker and Codex session lifecycle are implemented as a local Alpha. Python 3.11+, Git, and macOS or Linux are required. Windows is not supported (`fcntl` and POSIX process groups are used). [DeerFlow](deerflow.md), [enrolled SSH](ssh-worker.md), and the Go-authenticated workbench build on this Worker. Current delivery and limitations are tracked in [STATUS](STATUS.md); the dated live evidence below is historical, not a fresh native compatibility check.

## Install from this repository

```bash
git clone https://github.com/mzydmer/deermate.git
cd deermate
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp examples/local-worker.toml deermate.toml
```

Install from the default branch; no retired feature branch is required. On an Intel Mac where the latest cryptography dependency attempts a source build without OpenSSL, use the public wheel constraint documented in the [local installation guide](local-docker.md): `python -m pip install -e '.[dev]' 'cryptography==48.0.1'`.

Edit `deermate.toml`: set `projects.demo.root` to an existing **trusted** Git repository with at least one commit. Set a project-specific test command as an argv array. Omit `test_command` to collect a result with `needs_review` instead of claiming validated completion. Set `allow_write = true` only for projects you authorize the agent to edit.

Install Codex separately through its official distribution and run its supported login flow on the worker machine. DeerMate uses that existing local login; it does not copy or export credentials. If your Codex configuration has an unavailable model, set `model` to one currently available to your account. We do not automatically switch models when a provider rejects a request.

## Start the service

```bash
deermate --config deermate.toml serve
```

The listener binds only to `127.0.0.1:18777`. A bearer token is created at `.deermate/api.token` with mode `0600`; the state directory is `0700`. The CLI reads the file locally. Do not expose this HTTP server on the public internet or behind an external proxy. Requests with non-local Host headers or a browser Origin are rejected. Browser access uses the separate authenticated Go workbench, not a CORS-enabled Worker endpoint.

One process owns each state directory. A second service using that directory fails rather than running a competing dispatcher. Keep the database on a local disk.

## Submit and inspect

In another terminal, activate the same virtual environment:

```bash
deermate --config deermate.toml submit --project demo \
  --key login-fix-001 --prompt 'Fix the reported login validation bug. Keep the change focused.'
deermate --config deermate.toml list
deermate --config deermate.toml status TASK_ID
deermate --config deermate.toml events TASK_ID --after 0
deermate --config deermate.toml diff TASK_ID
```

The submission response contains `task_id`. Replace `TASK_ID` with that value. Repeating exactly the same submission key and request returns the same task; reusing a key with different content returns HTTP 409. Resume operations also require their own idempotency key.

The worker creates a detached Git worktree from the project's **committed HEAD**. Uncommitted changes in your main checkout are not copied or modified. Worktrees are retained under the state directory for inspection; automatic cleanup is not implemented.

Codex runs with a read-only or workspace-write sandbox, network access disabled, and no automatic permission escalation. After the native turn finishes, the configured test command runs through Codex's sandboxed `command/exec` interface, independently of the agent's prose. A bounded Git patch includes tracked changes and regular untracked files. Oversized or unsafe artifacts fail collection instead of being silently omitted.

## Interrupt, continue, and recover

For a follow-up with a separately retained result, use `deermate ... continue TASK_ID --key ROUND_KEY --message 'Next question'`. It returns a new child task, sharing the same native session/workspace. Use the new ID for subsequent questions and status; previous results remain readable. [Multi-round setup and chat integration](codex-conversation.md). The existing `resume` below updates the latest task in place for explicit recovery; stale parents with admitted children cannot resume.

```bash
deermate --config deermate.toml cancel TASK_ID
deermate --config deermate.toml resume TASK_ID \
  --key login-fix-followup-001 --message 'Continue with the smaller fix.'
```

`cancelling` means interruption was requested, not yet confirmed. Native `interrupted` events confirm normal turn cancellation. A cancellation during validation stops the owned app-server process group. A late cancellation that loses the race with native completion does not start a new validation command.

Process exit can precede asyncio's exit notification. Cleanup reconciles a signal lookup/permission error with a bounded wait for this instance's subprocess to exit. A live permission denial, changed process group or unconfirmed termination leaves the task `recovery_required`; it does not establish cancellation. Readers are released even on cleanup failure. Inspect the original task/session and verify that the old process has stopped before explicitly confirming recovery; the Worker does not signal a saved PID or automatically replay the request.

Collected validation output and the patch are saved while cleanup is pending. The Worker publishes a terminal result only after cleanup confirms; cleanup denial or interruption retains the evidence under `recovery_required`, without first announcing accepted completion.

If Codex requests supported form input, the task becomes `input_required`. Inspect events for question IDs, then provide a JSON object such as `{"choice": ["yes"]}`:

```bash
deermate --config deermate.toml answer TASK_ID --file answers.json
```

This form path is verified with the offline protocol fixture; whether a native Codex release sends it depends on its supported capabilities. Permission escalation is denied rather than translated into an auto-approval.

On service startup, queued tasks remain queued. Previously active tasks become `recovery_required`, retaining the native session ID, workspace, events, and policy snapshot. **The worker does not replay them automatically.** After checking that no old process is still working:

```bash
deermate --config deermate.toml resume TASK_ID --confirm-recovery \
  --key login-fix-recovery-001 --message 'Continue from the existing state.'
```

A continuation loads the existing native thread. If the original session identity was never acknowledged, the worker refuses to invent a replacement during resume. Submit a separate task explicitly after inspection. A changed project/runtime policy is rejected before dispatch; it cannot silently rebind existing work to new permissions.

## Results and limits

| State | Meaning |
| --- | --- |
| `completed` | Native turn completed, evidence was collected, and the configured validation command exited zero |
| `needs_review` | No validation command, a denied capability, or late cancellation requires explicit inspection |
| `failed` | Native failure, validation failure, incomplete evidence, timeout, or invalid configuration |
| `input_required` | A live supported question needs an answer |
| `cancelling` | Stop requested; execution may still be running |
| `cancelled` | Queued work was cancelled, or interruption/owned-process exit was confirmed |
| `recovery_required` | Service interruption left an uncertain outcome; no automatic replay |

A command exiting zero is a **receipt**, not proof of semantic correctness or of nonzero test coverage. The model may modify repository tests. Use trusted acceptance checks or independent review before accepting a patch. The original checkout and project Git metadata are shared with worktrees; a worktree is not an OS security boundary. Codex's configured environment, MCP connections, host read access, and sandbox behavior still matter. Use only trusted projects and a dedicated account/VM for sensitive work. There are no merge, push, deployment, or mail-sending tools provided by DeerMate in M1; this is not a claim that every external tool configuration is prevented from doing those things.

Prompts, native items, file paths, test output, and diffs are persisted locally and can contain private data. There is no database encryption or universal secret-redaction guarantee. The API rejects bodies larger than 64 KB and paginates events, but no long-term retention/total database quota is implemented yet.

## Verification

```bash
python -m pytest -q
ruff check src tests scripts/live_smoke.py
python -m build --wheel
```

The normal tests use an explicitly labeled offline JSON-RPC fixture and real temporary Git repositories/test commands. They make no model calls.

For an opt-in live test that uses your local Codex account and consumes model quota:

```bash
python scripts/live_smoke.py --live --model YOUR_AVAILABLE_MODEL
```

Add `--lifecycle` to also interrupt a real native turn and continue the same saved session.

The smoke script creates a temporary buggy repository, delegates its one-line repair to real Codex, runs a separate configured test command, prints a diff and receipt, and removes the temporary files afterward. It does not change your global Codex settings.

Historical native acceptance on 2026-10-25 used Python 3.12, macOS, Codex `0.164.0-alpha.11.1`, and an explicit `gpt-6.1-sol` model: a real repair completed, the independent test command ran one test and passed, and the patch was collected. That opt-in lifecycle run interrupted a real native turn and continued the same thread successfully across three attempts. Later [cloud-to-home](verification/home-link-2026-10-28.json) and [three-round conversation](verification/codex-conversation-live-2026-10-29.json) receipts include real model/native execution over a separately approved temporary link; same-host SSH fixtures remain distinct evidence.

The 2026-11-16 lifecycle repair runs offline: real temporary subprocesses expose the reaping/publication race, injected EPERM/ESRCH cover its signal-error boundaries, and live-child denial stays unconfirmed. Worker tests retain the task/session/turn, require explicit recovery and prove no new thread or turn on restart. See the [current receipt](verification/worker-lifecycle-2026-11-16.json). This run does not renew device authorization, invoke Codex or consume model quota.
