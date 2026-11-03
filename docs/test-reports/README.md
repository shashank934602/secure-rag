# Independent test reports

Each phase is checked by an independent tester before its release is tagged: the UI (Swagger `/docs`, the OpenAPI
document), the backend API (auth, status codes, validation, errors), and the functionality end to end with real models,
plus every test suite and the phase's evaluations. The tester reports and never changes code; every finding is fixed or
logged as an issue (`context/issue-tracker.md`), and the triage is recorded in `CHANGELOG.md`.

| Report | Release | Verdict | Triage |
|--------|---------|---------|--------|
| [v0.5.0.md](v0.5.0.md) | Phase 5 guardrails | release with known issues (no critical/high) | T-1, T-3, T-4, T-5 fixed in `v0.5.1`; T-6 → ISS-055; T-8, T-9 → ISS-056; T-7 → ISS-048 |
