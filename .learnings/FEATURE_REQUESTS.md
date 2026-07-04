# Feature Requests

Capabilities requested by the user.

---

## [FEAT-20260628-001] cloud_offline_automation

**Logged**: 2026-06-28T08:20:43+08:00
**Priority**: high
**Status**: pending
**Area**: infra

### Requested Capability
User wants automation tasks to run even when local computer is offline/sleeping. Looking for cloud-based "loop" alternatives that can execute independently.

### User Context
WorkBuddy automations are local-only; if computer sleeps at scheduled time, the task is missed entirely. User has missed 2 days of runs (June 26-27) because computer wasn't online at 9:30 AM.

### Complexity Estimate
medium — GitHub Actions already exist but are limited (no AI search, anti-crawling issues). Could enhance to push directly to repo, or use webhook-triggered approach.

### Suggested Implementation
1. Enhance GitHub Actions workflow to auto-update index.html directly (currently only creates Issues)
2. Or: GitHub Actions detects new regs → sends notification → user runs local skill when convenient
3. Or: macOS scheduled wake + prevent sleep at automation time

### Metadata
- Frequency: recurring
- Related Features: apac-trade-compliance-updater Skill, auto_update.yml GitHub Actions
