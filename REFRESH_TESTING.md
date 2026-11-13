# Refresh scheduling candidate (0.3.1)

Branch: `fix/refresh-scheduling`. Base: `1c6132641f323280dccda47797560b9c42e6760f` (main 0.3.0).

Status: candidate only. The 0.3.0 desktop acceptance is historical evidence and does **not** approve this change. Main must remain unchanged until the owner tests this candidate on the affected desktop. Record the exact tested commit, Omarchy version, monitors and poll interval in the PR.

## Failure paths covered

- Previously, a monitor's refresh button knew only its own pending action. Other monitors could enqueue duplicate requests. Busy/idle is now shared and enforced by the service, including races before the UI receives a broadcast.
- An unexpected worker exception could permanently stop future jobs. The worker now recovers, releases busy state, reports a generic error and permits automatic retry.
- A single polling budget could starve later accounts. Each account now runs with its own network budget and a killable 70-second watchdog. Timeout preserves its last count and the sweep continues. Account results are published as they finish.
- Periodic polling uses monotonic elapsed time since sweep completion, preventing overlapping sweeps. Overdue polling takes priority over repeated detail requests. Partial account failures retain their individual backoff; fatal sweep errors retry after at least 30 seconds.
- A blocked monitor socket no longer holds the shared service lock. Its bounded outgoing queue disconnects it if it cannot keep up; the widget reconnects to current state. Supervisor snapshot-lock waits are bounded as well.

These are reproduced/tested failure paths, not a claim that every one caused the owner's particular incident.

## Automated validation

Run the full commands in TESTING.md. New regressions cover two real monitor connections, 100 overlapping refresh clicks, busy/idle propagation, counters decreasing to zero, a failed first account with a second account still queried, preserved rate-limit backoff, periodic polling after manual refresh/failure, exception recovery, a child ignoring termination, cancellation, malformed worker output, pipe-only private requests and retained settings/OAuth-client data. Existing upgrade/rollback and real isolated Secret Service checks remain required. Qt parsing and the JavaScript checks do not observe the rendered desktop.

## Install on the existing test desktop

Run the status command first. If it prints changes, preserve them and stop before switching. No credential or state files should be deleted or reset.

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
git status --short
git fetch origin fix/refresh-scheduling
omarchy plugin disable eprom.gmail-notifier
git switch --detach origin/fix/refresh-scheduling
git rev-parse HEAD
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Do not use the normal updater during this test; it follows main. Existing accounts and OAuth authorization must be reused.

If the old 0.3.0 service is already frozen, disabling its widgets may leave that old process running. A local diagnostic session should identify and stop only the old plugin helper's `serve` process before enabling this candidate; never kill all Python processes or reset credentials. New candidate queries are cancelled when all monitor clients disconnect.

## Required desktop checks — pending owner confirmation

1. On at least two monitors with several enabled accounts, send synthetic mail to each account. Refresh on one monitor. Verify every account's count changes on all monitors, even if the count decreases to zero after reading/deleting messages in Gmail.
2. During the query, check that refresh and load-more are disabled on every monitor and reenabled when it finishes. Click rapidly on different monitors; there should be one active query and no accumulated refreshes afterward.
3. Click a flashing account during a query. Acknowledgement must stop flashing on all monitors; its panel should load details once the service is free. Switching/closing panels must not produce a repeating detail-query loop.
4. After a manual refresh, send another synthetic email and **wait through at least two configured intervals without clicking refresh or restarting the plugin**. Verify automatic counts and flashing continue on all monitors.
5. Interrupt the network, refresh, then restore connectivity. Verify an error appears, saved counts remain, controls recover and later automatic polling succeeds. One failing account must not prevent healthy accounts later in the list from being queried. A severely stuck account may take up to 70 seconds before the next account starts.
6. Change a label, notification switch or pause state on another monitor during a query. Verify the edit persists. Reenable paused accounts and refresh; restart the shell and repeat the automatic interval check.
7. Confirm accounts, order, initials, settings and saved OAuth authorization are unchanged through installation and rollback. Do not post personal snapshots, OAuth files or tokens in the PR.
8. With no new mail, observe process counts and CPU for several intervals. Per-account worker processes exist only during queries; they must exit afterward. The shared service and persistent monitor clients stay running.

## Return to stable

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
omarchy plugin disable eprom.gmail-notifier
git switch main
git pull --ff-only origin main
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Do not remove `~/.config/omarchy/gmail-notifier`, its private backup, header caches, OAuth client or Secret Service entries. This candidate retains the existing storage format and Google scope.
