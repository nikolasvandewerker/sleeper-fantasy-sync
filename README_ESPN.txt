ESPN Sync Add-on (October 2026)

Keep your existing sync.py and data/sleeper_snapshot.json unchanged.

Upload these two files to the same paths in your GitHub repository:
  espn_sync.py                              (repository root)
  .github/workflows/sleeper-sync.yml        (REPLACE existing workflow)

GitHub Actions secrets must already exist: ESPN_S2, ESPN_SWID.

In Actions -> Fantasy league sync -> Run workflow, start a manual test.
The successful run should create data/espn_snapshot.json.
If ESPN access is rejected, the action will fail and will NOT overwrite a previous ESPN snapshot.

IMPORTANT PRIVACY NOTE: data/espn_snapshot.json will be publicly visible if the repository
is public. It contains all 10 team rosters for each league, but intentionally excludes
owner names, member IDs, emails and session cookies. Do not upload any credential values.
If this is not acceptable, do not run the workflow; instead use a private repository and
an authenticated publishing mechanism for a minimal per-user summary.

The ESPN endpoint is unofficial; cookies can expire. ESPN lineup_slot_id values are
numeric and can be interpreted later using ESPN's position-slot mappings. The snapshot
contains every team's roster but does not yet know which team ID is yours. After the
first successful run, identify your own team IDs so the briefing can focus on your roster.

The existing GitHub cron runs at 11:30 UTC (6:30 AM CDT / 5:30 AM CST).
