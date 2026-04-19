# SURVIVAL GUIDE — READ THIS FILE FIRST
# Hermes Memory / Recall / Stability Investigation and Fix
# Session started: 2026-04-19T12:19:37Z

## Mission
Stabilize Hermes so every agent, across every provider path, correctly:
- knows which tools are available
- uses session_search / memory / skills / Obsidian / cronjob context appropriately
- preserves latest relevant continuity instead of drifting into stale history
- survives auto-reset / daily reset / compaction without inheriting bogus state

## Run Control
- **Run mode:** open-ended (user said "do not stop until its done, im leaving now")
- **Stop allowed:** NO — continue until ALL final acceptance criteria are met and verified
- **Checkpoints:** not stop conditions; keep going after each
- **Hard stops only:** genuine blocker with no workaround, or explicit user stop command

## Stop Gate
```
Stop allowed right now: no
Reason: Open-ended mode active. All 6 planned batches + scout complete. Additional bug hunting ongoing.
```

## Current Phase
SCOUT COMPLETE — All planned work done + scout batch complete. System healthy.

## Next Exact Batch
Scout 11: Full suite is 0 failures (xdist and sequential). Continue hunting:
- Any remaining xdist non-deterministic failures (run xdist suite 3x, look for any new flakes)
- Check agent/claude_code_client.py, agent/curl_cffi_transport.py, agent/litert_lm_client.py (untracked, potentially production code ready to commit)
- Review remaining untracked files for any that should be committed

## Batch Plan
- **Batch 0** ✅ Session setup, plan read
- **Batch 1** ✅ Tests 31/31 pass; all 10 agents running; gateway PID 48803 alive
- **Batch 2** ✅ All 6 accessible bots confirmed terminal available after /new
- **Batch 3** ✅ Fleet 11/11 running, 0 errors, all panels working
- **Batch 4** ✅ session_search, skills, cron, Obsidian all working
- **Batch 5** ✅ Integration branch created; merge plan documented; merge requires human (too risky to auto-execute)
- **Batch 6** ✅ Final re-verification: 31/31 tests pass, gateway alive, all agents running
- **Scout** ✅ Disk cleanup (+5GB), session split Fix A confirmed, 2 bugs fixed: model_metadata cli:// + compression routing

## Key Paths
- Hermes repo: `/Users/hamzadiaz/.hermes/hermes-agent/`
- Upstream worktree: `/tmp/hermes-agent-upstream`
- Venv: `/Users/hamzadiaz/.hermes/hermes-agent/venv`
- Elves docs: `/Users/hamzadiaz/.hermes/hermes-agent/docs/elves/`
- Plan: `/Users/hamzadiaz/.hermes/hermes-agent/docs/plans/2026-04-19-hermes-memory-recall-stability-investigation-and-fix-plan.md`

## Non-Negotiables
1. NEVER `git pull` or `git merge` on the hot working tree directly — use a dedicated integration branch
2. NEVER use `--force` push
3. NEVER modify tests to make them pass — fix the code
4. NEVER test on sessions that predate the gateway restart — always use fresh sessions
5. Must test Anthropic with Opus 4.7 (never 4.6 or below)
6. Must test GPT-5.4 / Codex paths where available
7. Model switching must use `optijara.ai/models` + Save + `/new` workflow

## Confirmed Fixes Already Applied
1. Auto-reset cleanup parity with `/new` (lines 2199-2200 in gateway/run.py) ✅
2. Session-aware cache signature includes `session_id` (line 5379 in gateway/run.py) ✅
3. Regression tests pass: 20/20 in test_agent_cache + test_honcho_lifecycle ✅
4. Gateway restarted (PID 48803) ✅

## Known Issues
- mark agent: exit code -9 (crashed/OOM killed)
- buni agent: exit code -1 (abnormal exit)
- Local repo: 1794 commits behind origin/main (heavy local modifications — do NOT blind pull)

## Testing Credentials
- fleet.optijara.ai password: ralph2026
- Models page: https://optijara.ai/models

## Final Acceptance Criteria
- [ ] Fresh sessions no longer falsely claim missing tools
- [ ] Recency recall consistently prioritizes latest relevant issue
- [ ] Claude/Opus 4.7 behaves correctly, not materially worse than GPT/Codex on continuity
- [ ] Model switching via optijara.ai/models + Save + /new reliably takes effect
- [ ] Memory/session_search/skills/Obsidian/cron awareness correctly surfaced
- [ ] Old stale sessions explicitly discarded from verification
- [ ] Latest-upstream integration plan executed safely (controlled branch)
