"""Fetch ESPN league rosters with GitHub Actions secrets; publish sanitized snapshot.

ESPN's private fantasy endpoints are unofficial and may change or revoke access.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LEAGUES = {'2026 Pop-a-Top': 820491, 'MUDCATS': 415719}
SEASON = 2026
DEST = Path('data/espn_snapshot.json')


def get_league(league_id, cookies):
    root = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{league_id}'
    url = root + '?' + urlencode([('view', 'mRoster'), ('view', 'mTeam'), ('view', 'mSettings')])
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; FantasyLeagueSync/1.0)',
        'Accept': 'application/json',
        'Cookie': cookies,
    })
    with urlopen(req, timeout=45) as response:
        return json.load(response)


def roster_entries(team):
    result = []
    for entry in (team.get('roster') or {}).get('entries', []):
        player = (entry.get('playerPoolEntry') or {}).get('player') or {}
        result.append({
            'player_id': player.get('id') or entry.get('playerId'),
            'name': player.get('fullName') or player.get('name'),
            'lineup_slot_id': entry.get('lineupSlotId'),
            'injury_status': player.get('injuryStatus'),
            'pro_team_id': player.get('proTeamId'),
            'default_position_id': player.get('defaultPositionId'),
        })
    return result


def sanitize(raw):
    settings = raw.get('settings') or {}
    roster_settings = settings.get('rosterSettings') or {}
    scoring = settings.get('scoringSettings') or {}
    return {
        'league_id': raw.get('id'),
        'league_name': settings.get('name'),
        'season': raw.get('seasonId'),
        'week': raw.get('scoringPeriodId'),
        'team_count': settings.get('size'),
        'lineup_slot_counts': roster_settings.get('lineupSlotCounts'),
        'scoring_type': scoring.get('playerRankType'),
        'scoring_items': scoring.get('scoringItems'),
        # No owners, member identifiers, emails, cookies, or private account fields.
        # Team IDs/rosters are visible in the public JSON: assess privacy before enabling.
        'teams': [
            {
                'team_id': team.get('id'),
                'record': {
                    'wins': ((team.get('record') or {}).get('overall') or {}).get('wins'),
                    'losses': ((team.get('record') or {}).get('overall') or {}).get('losses'),
                },
                'roster': roster_entries(team),
            }
            for team in raw.get('teams') or []
        ],
    }


def main():
    s2 = os.environ.get('ESPN_S2', '').strip()
    swid = os.environ.get('ESPN_SWID', '').strip()
    if not s2 or not swid:
        print('ESPN secrets missing. Add ESPN_S2 and ESPN_SWID to repository Actions secrets.', file=sys.stderr)
        return 1
    # Do not log cookie values or raw ESPN response.
    cookie_header = f'espn_s2={s2}; SWID={swid}'
    output = {'updated_at_utc': datetime.now(timezone.utc).isoformat(), 'leagues': {}}
    for name, league_id in LEAGUES.items():
        try:
            league = sanitize(get_league(league_id, cookie_header))
        except HTTPError as exc:
            print(f'{name}: ESPN returned HTTP {exc.code}. Verify cookie validity and league access.', file=sys.stderr)
            return 1
        except (URLError, TimeoutError, ValueError) as exc:
            print(f'{name}: failed to fetch or parse ESPN response ({type(exc).__name__}).', file=sys.stderr)
            return 1
        if not league['teams'] or not any(team['roster'] for team in league['teams']):
            print(f'{name}: roster data missing; refusing to publish an empty snapshot.', file=sys.stderr)
            return 1
        output['leagues'][name] = league
        print(f'{name}: retrieved {len(league["teams"])} teams and their rosters.')
    DEST.parent.mkdir(exist_ok=True)
    DEST.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {DEST}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
