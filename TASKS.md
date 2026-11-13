# Review tasks 7–18

## Follow-up: OAuth setup help (0.3.2 candidate)

The focused branch `fix/oauth-setup-help` adds a prominent bilingual help entry for missing/invalid/unreadable Google client files, an eight-step first-install guide, a separate three-step recovery route for saved accounts, official Google links and a read-only setup check. Account/client/credential continuity remains a permanent requirement. Automated upgrade/recovery and localized Qt guide checks are included; actual Omarchy desktop acceptance remains pending in [OAUTH_HELP_TESTING.md](OAUTH_HELP_TESTING.md). The focused help PR builds on the 0.3.1 refresh candidate; both must be tested and integrated in order before release.

## Follow-up: refresh scheduling (0.3.1 candidate)

The owner's report of intermittent frozen polling prompted the isolated branch `fix/refresh-scheduling`. The candidate implements shared busy state, overlap rejection, per-account process deadlines, worker recovery, monotonic periodic scheduling and nonblocking monitor delivery. Automated coverage is added in `tests/test_refresh_scheduling.py` and `tests/widget.test.cjs`. Desktop acceptance is **pending**; see [REFRESH_TESTING.md](REFRESH_TESTING.md). This follow-up does not invalidate or extend the historical 0.3.0 acceptance below.

## Historical audit

Version 0.3.0 follows the audit of main at 5adaad8. Tasks 7–18 are implemented. The owner confirmed successful desktop testing and approved integration on 2026-11-06; evidence and its limits are recorded in ACCEPTANCE.md. Marketplace approval is a separate maintainer decision.

| Task | Implementation | Evidence / remaining check |
|---|---|---|
| 7 Private notification transport | Implemented: Gio D-Bus and libsecret in process; no private argv in widget requests | Real isolated notification server and CI keyring migration check; owner confirmed desktop functionality |
| 8 Ordered synchronization | Implemented: one ordered stream with epoch/revision per service | Stale snapshot rejection and two persistent client integration |
| 9 Concurrent settings | Implemented: owner-only short transaction, atomic files, lifecycle generation checks | Multiprocess edits and pause during poll tests |
| 10 Reattempts and queued actions | Implemented: explicit details retry and bounded queue | No automatic repeated details; actions processed sequentially |
| 11 Header pages | Implemented: 50-message pages, header cache reuse | 501 unread messages preserve total and load pages |
| 12 Invalid state/data recovery | Implemented: bounded JSON, account/header/page validation and config backup | Corrupt configuration preserved and structured error; invalid responses rejected |
| 13 Deadlines/error handling | Implemented: 60-second network budget, per-request deadlines, bounded pages and rate-limit backoff | Controlled timeout/rate-limit and notification-failure tests |
| 14 OAuth and upgrade continuity | Implemented: original credentials retained, compatible copies synchronized, callbacks and cancellation validated | Upgrade/rollback fixtures and real keyring integration; owner confirmed authorization reuse through update and rollback |
| 15 Idle work | Implemented: one service and persistent clients, push updates and no periodic process starts | Multiple client and unchanged-state tests; long-term desktop power/CPU measurement remains follow-up monitoring |
| 16 Omarchy UI integration | Implemented: live locale with English/Spanish catalogs, theme reset, explicit retry/load-more and cancel controls | Qt parsing and widget tests; owner confirmed desktop functionality; individual layout variants were not itemized |
| 17 Regression coverage | Implemented for code paths and IPC | See TESTING.md and owner-reported desktop acceptance in ACCEPTANCE.md |
| 18 Documentation/version | Updated README, TESTING, CHANGELOG and version 0.3.0 | Final marketplace report must bind to the accepted commit |

Owner approval for integration is recorded in ACCEPTANCE.md. After merging, request marketplace revalidation of the exact final main commit. The previous marketplace reply described the wrapper migration; it did not eliminate the argv exposure. The candidate corrects that by removing the process boundary from desktop IPC.

Update compatibility is a permanent release requirement in COMPATIBILITY.md and AGENTS.md. The upgrade suite must pass before any future release; plugin updates may not require OAuth again merely because code or version changed. External Google revocation/expiry is diagnosed separately.
