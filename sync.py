import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

USER_ID = '1394804934028853248'
LEAGUES = {'Pour Boiz': '1393422439593021442', 'The Up and Downers': '1401329866044878848'}
BASE = 'https://api.sleeper.app/v1'

def fetch(path):
    req = Request(BASE + path, headers={'User-Agent': 'PersonalSleeperBriefing/1.0'})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

state = fetch('/state/nfl')
week = state.get('week') or state.get('leg')
players = fetch('/players/nfl')

def player_name(pid):
    if not pid or pid == '0':
        return None
    item = players.get(str(pid), {})
    return item.get('full_name') or item.get('search_full_name') or str(pid)

trending = fetch('/players/nfl/trending/add?lookback_hours=24&limit=100')

output = {'updated_at_utc': datetime.now(timezone.utc).isoformat(), 'season': state.get('season'), 'week': week, 'leagues': {}}
for name, league_id in LEAGUES.items():
    league = fetch(f'/league/{league_id}')
    rosters = fetch(f'/league/{league_id}/rosters')
    mine = next(r for r in rosters if r.get('owner_id') == USER_ID or USER_ID in (r.get('co_owners') or []))
    occupied = set().union(*(set(r.get('players') or []) for r in rosters))
    starters = mine.get('starters') or []
    bench = [pid for pid in (mine.get('players') or []) if pid not in starters]
    matchups = fetch(f'/league/{league_id}/matchups/{week}') if week else []
    my_matchup = next((m for m in matchups if m.get('roster_id') == mine['roster_id']), None)
    opponent = next((m for m in matchups if my_matchup and m.get('matchup_id') == my_matchup.get('matchup_id') and m.get('roster_id') != mine['roster_id']), None)
    output['leagues'][name] = {
        'league_id': league_id, 'roster_id': mine['roster_id'],
        'record': {'wins': mine['settings'].get('wins'), 'losses': mine['settings'].get('losses')},
        'scoring': league.get('scoring_settings'), 'lineup_positions': league.get('roster_positions'),
        'starters': [{'id': pid, 'name': player_name(pid), 'slot': slot} for pid, slot in zip(starters, league.get('roster_positions', []))],
        'bench': [{'id': pid, 'name': player_name(pid)} for pid in bench],
        'reserve': [{'id': pid, 'name': player_name(pid)} for pid in (mine.get('reserve') or [])],
        'opponent_roster_id': opponent.get('roster_id') if opponent else None,
        'recent_transactions': fetch(f'/league/{league_id}/transactions/{week}') if week else [],
        'unrostered_trending_adds': [
            {'id': p['player_id'], 'name': player_name(p['player_id']), 'adds': p.get('count')}
            for p in trending if p.get('player_id') not in occupied
        ][:20],
    }

Path('data').mkdir(exist_ok=True)
Path('data/sleeper_snapshot.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
print('Updated data/sleeper_snapshot.json')
