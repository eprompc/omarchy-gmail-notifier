# Changelog

## 0.3.1 — candidate, desktop acceptance pending

- Share network busy state across monitors, disable refresh/load controls during queries, and reject overlapping network requests without building a queue.
- Isolate each account query in a supervised process with a hard deadline; continue to other accounts after a timeout and publish completed accounts incrementally.
- Recover the network worker after unexpected exceptions, give overdue polls priority over details, and schedule the next interval after each completed sweep.
- Keep slow monitor connections outside the service lock; bound snapshot bookkeeping waits and retain account rate-limit backoff.
- Preserve configuration paths, OAuth scope and saved Secret Service authorizations. Private worker requests/results use pipes; desktop IPC remains in process.
- Add refresh burst, multi-monitor busy/idle, stalled process, periodic recovery, state preservation and UI regressions. Desktop acceptance for this candidate is recorded separately in REFRESH_TESTING.md.

## 0.3.0 — 2026-11-06

- Deliver notifications through Gio D-Bus inside the helper process; access credentials with libsecret in process; preserve and synchronize legacy entries for updates and rollback.
- Preserve account initials, sender and subject in transient desktop notifications without placing them in child-process arguments.
- Share an owner-only local service across monitors, with persistent clients, ordered revisions and an action queue.
- Protect configuration edits with short transactions and a private backup; reject invalid state without silently deleting configuration.
- Paginate header details in groups of 50 and reuse cached headers, including inboxes above 500 unread messages.
- Bound network operations and pagination; keep counters when desktop notification delivery fails; recover from rate limits and temporary errors.
- Follow Omarchy's live locale, preserve explicit English/Spanish preferences, update theme handling and stop idle flash clocks.
- Add isolated D-Bus and private-socket integration tests, widget state/queue regressions and Qt 6 syntax checks.
