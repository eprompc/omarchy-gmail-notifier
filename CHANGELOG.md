# Changelog

## 0.3.0 — 2026-11-06

- Deliver notifications through Gio D-Bus inside the helper process; access credentials with libsecret in process; preserve and synchronize legacy entries for updates and rollback.
- Preserve account initials, sender and subject in transient desktop notifications without placing them in child-process arguments.
- Share an owner-only local service across monitors, with persistent clients, ordered revisions and an action queue.
- Protect configuration edits with short transactions and a private backup; reject invalid state without silently deleting configuration.
- Paginate header details in groups of 50 and reuse cached headers, including inboxes above 500 unread messages.
- Bound network operations and pagination; keep counters when desktop notification delivery fails; recover from rate limits and temporary errors.
- Follow Omarchy's live locale, preserve explicit English/Spanish preferences, update theme handling and stop idle flash clocks.
- Add isolated D-Bus and private-socket integration tests, widget state/queue regressions and Qt 6 syntax checks.
