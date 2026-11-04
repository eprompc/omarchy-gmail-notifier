# Testing the multi-monitor branch

This branch is experimental. Keep the pull request in draft until the desktop
checks below pass. Automated tests do not start Omarchy or authenticate to Google.

## Automated regression checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 -m compileall -q helper
```

These cover shared alert generations, acknowledgement from another process,
concurrent clicks, delayed clicks after new mail, equal-count message replacement,
expiration, pause filtering, removal and local reads while the Gmail lock is held.
JavaScript checks cover shared activity and flash phase. GitHub Actions runs these
checks on pull requests and pushes to main and fix branches.

## How Omarchy updates this plugin

The upstream `omacom/omarchy` scripts on branch `quattro`, inspected on 2026-11-04,
clone the repository's default branch. `bin/omarchy-plugin-update` runs
`git fetch origin HEAD` and fast-forwards to `FETCH_HEAD`; it does not select a
GitHub release or the locally checked-out development branch. The default branch
of this repository is `main`. Publishing a branch or draft PR therefore does not
offer its changes through the normal updater. Merging to main does.

Do not use `omarchy plugin update` while testing a development checkout: it still
targets the remote default HEAD. Do not change the repository default branch.
Your installed Omarchy version may differ; inspect its update script if needed.

Sources:
- https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-plugin-add
- https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-plugin-update

## Try the branch on your desktop

The CLI currently has no branch flag for `plugin add`. Use the existing installed
checkout. The commands below require its current branch to be `main` and the
checkout to have no uncommitted changes. Stop if either check differs; preserve
your edits before switching versions. Do not install a second copy with the same
plugin ID.

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
git status --short
git branch --show-current
git fetch origin fix/multi-monitor
omarchy plugin disable eprom.gmail-notifier
git switch --detach origin/fix/multi-monitor
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Use the already configured Gmail accounts. The first successful poll establishes
the new alert baseline; existing unread mail should not flash just because you
installed the branch. This version adds `alerts.json` and `alerts.lock` alongside
the existing configuration; it does not migrate OAuth tokens or the config schema.
Do not attach these personal runtime files to issues or PRs.

To return to the stable checkout, disable the plugin, switch back and enable it:

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
omarchy plugin disable eprom.gmail-notifier
git switch main
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

## Desktop acceptance checklist (required before merging)

Record the Omarchy version, monitor count, scaling and PR commit tested.

- [ ] Validate the plugin and enable it on two and three monitors without QML errors.
- [ ] After the baseline poll, receive mail: all badges show the same count and
      share the same flash timing. Repeat with desktop notifications disabled.
- [ ] Click a flashing account on each monitor in turn: all copies stop. Verify
      propagation normally follows the file-change event; the local fallback is
      five seconds if an event is missed.
- [ ] Test both timed flashing and flash-until-clicked. Opening another monitor
      or restarting the widget must not restart an acknowledged or expired alert.
- [ ] Receive a new email at the same time as a click. The click only acknowledges
      the displayed event; the newer event remains active.
- [ ] Read/archive one unread email and receive a different one between polls:
      the unchanged unread count must still produce a new alert.
- [ ] Pause all accounts on one monitor and resume on another; also remove all
      accounts and add one. Every monitor must pick up those local changes.
- [ ] Open a long unread list or interrupt networking while another alert is
      flashing; acknowledging it must not wait for the Gmail request to finish.
- [ ] Disconnect/reconnect a monitor, restart the shell, and test mixed scaling.
- [ ] Return to main and verify the stable widget still works.

Configuration write concurrency, header pagination, broader error recovery and
OAuth diagnostics remain separate follow-up tasks. This PR specifically changes
shared alert state and monitor synchronization.
