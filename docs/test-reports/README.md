# Independent test reports

Each phase is checked by an independent tester before its release is tagged: the UI (Swagger `/docs`, the OpenAPI
document), the backend API (auth, status codes, validation, errors), and the functionality end to end with real models,
plus every test suite and the phase's evaluations. The tester reports and never changes code; every finding is fixed or
logged as an issue (`context/issue-tracker.md`), and the triage is recorded in `CHANGELOG.md`.

| Report | Release | Verdict | Triage |
|--------|---------|---------|--------|
| [v0.5.0.md](v0.5.0.md) | Phase 5 guardrails | release with known issues (no critical/high) | T-1, T-3, T-4, T-5 fixed in `v0.5.1`; T-6 → ISS-055; T-8, T-9 → ISS-056; T-7 → ISS-048 |
| [v0.6.0.md](v0.6.0.md) | Phase 6 audit trail | release with known issues (no critical/high) | T-1, T-2, T-4, T-5 fixed in `v0.6.0`; T-3 no action; T-6 claim corrected; T-7 → ISS-057, ISS-058; T-9 → ISS-048; T-10 is ISS-019 |
| [v0.6.0-retest.md](v0.6.0-retest.md) | Phase 6 fixes (commit `4732b21`) | release | T-1, T-2, T-4, T-5 confirmed fixed on a real server; no regressions, no new findings |
| [v0.7.0.md](v0.7.0.md) | Phase 7 eval gate | release with known issues (no critical/high) | T-1, T-2, T-3, T-6, T-7 fixed; T-4, T-5, T-8 hardened (CODEOWNERS, step-level keys) with the rest → ISS-063; T-9, T-10 lesson corrected |
| [v0.8.0.md](v0.8.0.md) | Phase 8 ship it | release with known issues (no critical/high); fresh clone → first answer 6.5 min | T-1, T-2, T-4 fixed; T-3 → ISS-070 (and README build time); T-5 observations |
