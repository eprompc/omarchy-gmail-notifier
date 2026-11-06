# Review tasks 7–18

Candidate 0.3.0 follows the audit of main at 5adaad8. “Implemented” means code and focused automated checks are present; it does not mean a marketplace approval or a rendered desktop acceptance pass.

| Task | Implementation | Evidence / remaining check |
|---|---|---|
| 7 Private notification transport | Implemented: Gio D-Bus and libsecret in process; no private argv in widget requests | Real isolated notification server and CI keyring migration check; desktop acceptance pending |
| 8 Ordered synchronization | Implemented: one ordered stream with epoch/revision per service | Stale snapshot rejection and two persistent client integration |
| 9 Concurrent settings | Implemented: owner-only short transaction, atomic files, lifecycle generation checks | Multiprocess edits and pause during poll tests |
| 10 Reattempts and queued actions | Implemented: explicit details retry and bounded queue | No automatic repeated details; actions processed sequentially |
| 11 Header pages | Implemented: 50-message pages, header cache reuse | 501 unread messages preserve total and load pages |
| 12 Invalid state/data recovery | Implemented: bounded JSON, account/header/page validation and config backup | Corrupt configuration preserved and structured error; invalid responses rejected |
| 13 Deadlines/error handling | Implemented: 60-second network budget, per-request deadlines, bounded pages and rate-limit backoff | Controlled timeout/rate-limit and notification-failure tests |
| 14 OAuth | Implemented: unrelated callbacks ignored, local connection deadline, cancellation, validated token response and local secret removal errors | Synthetic callback tests; real Google/Secret Service acceptance pending |
| 15 Idle work | Implemented: one service and persistent clients, push updates and no periodic process starts | Multiple client and unchanged-state tests; desktop power/CPU measurement pending |
| 16 Omarchy UI integration | Implemented: live locale with English/Spanish catalogs, theme reset, explicit retry/load-more and cancel controls | Qt parsing and widget tests; rendered RTL/scaling/keyboard/animation checks pending |
| 17 Regression coverage | Implemented for code paths and IPC | See TESTING.md; real Omarchy session remains required |
| 18 Documentation/version | Updated README, TESTING, CHANGELOG and version 0.3.0 candidate | Final marketplace report must bind to the accepted commit |

Before release, record the desktop acceptance results in TESTING.md and obtain owner approval for the candidate. Then request marketplace revalidation of the final main commit. The previous marketplace reply described the wrapper migration; it did not eliminate the argv exposure. The candidate corrects that by removing the process boundary from desktop IPC.
