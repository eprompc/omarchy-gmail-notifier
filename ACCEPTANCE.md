# 0.3.0 acceptance record

Date: 2026-11-06.

Executable code tested: `131a20b41174968019e33bc72826b626bfa8709f` on `fix/privacy-reliability-45` (PR #2). Release documentation updates after that commit do not change executable code.

## Automated evidence

GitHub Actions passed the 48 Python regressions, JavaScript checks, real isolated notification and Secret Service integrations, Python compilation and Qt 6 QML parsing. The Omarchy 4.5 manifest validator accepted the plugin. A local execution of the marketplace's public static analysis returned `passed` without findings or additional capabilities; this is not the marketplace's official approval.

## Owner-reported desktop evidence

The owner ran the candidate on the target desktop and reported:

- The automated checks and the upgrade to the candidate passed.
- Accounts and saved settings were preserved.
- Rolling back to the previous commit reused the accounts without another OAuth authorization.
- Restoring the candidate left version 0.3.0 enabled at the expected commit, with a clean repository.
- Two persistent processes per monitor and a shared service were observed; the report initially described idle-count stability as still under observation.
- After conducting the desktop tests, the owner explicitly confirmed that everything worked correctly and authorized merging to main and preparing the marketplace reply.

The local coding session did not itself observe the rendered UI. The owner's subsequent desktop confirmation is the visual acceptance evidence. Exact monitor count, scaling and individual visual variants were not itemized in the report; they must not be invented. Long-term CPU/power measurements are follow-up monitoring, not claimed as a measured benchmark here.

## Release decision and compatibility

The owner approved integration of the tested code. Future updates must preserve saved settings and usable authorization under COMPATIBILITY.md and AGENTS.md. Google revocation/expiry and unavailable external desktop services remain separately diagnosed conditions, not reasons to silently reset personal state.

Marketplace listing/verification remains subject to a fresh exact-commit report and the maintainer's decision after integration.
