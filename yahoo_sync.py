"""Read-only Yahoo Fantasy Football sync. Never log OAuth credentials or raw responses."""
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
DEST = Path("data/yahoo_snapshot.json")
SEASON = 2026

def request_json(url, token):
    req = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=40) as response:
            return json.load(response)
    except HTTPError as exc:
        endpoint = url.split("?")[0].split("/fantasy/v2/")[-1]
        print("Yahoo Fantasy endpoint denied: " + endpoint + " (HTTP " + str(exc.code) + ")", file=sys.stderr)
        raise

def refresh():
    client = os.environ["YAHOO_CLIENT_ID"].strip()
    secret = os.environ["YAHOO_CLIENT_SECRET"].strip()
    refresh_token = os.environ["YAHOO_REFRESH_TOKEN"].strip()
    auth = base64.b64encode((client + ":" + secret).encode()).decode()
    body = urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode()
    req = Request(TOKEN_URL, data=body, headers={
        "Authorization": "Basic " + auth,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }, method="POST")
    with urlopen(req, timeout=40) as response:
        result = json.load(response)
    token = result.get("access_token")
    if not token:
        raise ValueError("Yahoo did not return an access token")
    new_refresh = result.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        # Do not print or commit either refresh token.
        print("WARNING: Yahoo returned a changed refresh token. The GitHub secret must be updated securely before the old token stops working.", file=sys.stderr)
    return token

def objects(node, key):
    """Walk Yahoo's JSON envelope, including numbered object keys."""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                if isinstance(v, list):
                    found.extend(v)
                elif isinstance(v, dict):
                    found.append(v)
            found.extend(objects(v, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(objects(item, key))
    return found

def first(node, key, default=None):
    if isinstance(node, dict) and key in node:
        return node[key]
    matches = objects(node, key)
    return matches[0] if matches else default

def player_info(player):
    p = player.get("player", player)
    name = first(p, "name", {})
    if not isinstance(name, dict):
        name = {}
    selected = first(p, "selected_position", {})
    if not isinstance(selected, dict):
        selected = {}
    return {
        "player_key": first(p, "player_key"),
        "name": name.get("full") or first(p, "full"),
        "team": first(p, "editorial_team_abbr"),
        "position": first(p, "display_position"),
        "selected_position": first(selected, "position"),
        "status": first(p, "status"),
        "injury_note": first(p, "injury_note"),
        "bye_weeks": first(p, "bye_weeks"),
    }

def main():
    for name in ("YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET", "YAHOO_REFRESH_TOKEN"):
        if not os.environ.get(name):
            print("Missing required GitHub Actions secret: " + name, file=sys.stderr)
            return 1
    try:
        token = refresh()
        try:
            data = request_json(API + "/users;use_login=1/games;game_codes=nfl?format=json", token)
        except HTTPError as primary_error:
            if primary_error.code == 403:
                # Diagnostic only: compare a public game endpoint with the account endpoint.
                try:
                    request_json(API + "/game/nfl?format=json", token)
                    print("Yahoo diagnostic: public game endpoint succeeded; account-scoped endpoint denied.", file=sys.stderr)
                except HTTPError as probe_error:
                    print("Yahoo diagnostic: public game endpoint HTTP " + str(probe_error.code) + ".", file=sys.stderr)
                except (URLError, TimeoutError, ValueError):
                    print("Yahoo diagnostic: public game endpoint could not be evaluated.", file=sys.stderr)
            raise
        games = [g for g in objects(data, "game") if str(first(g, "season", "")) == str(SEASON)]
        if not games:
            raise ValueError("No Yahoo NFL game for the requested season")
        game_key = first(games[0], "game_key")
        if not game_key:
            raise ValueError("Yahoo game key missing")
        league_data = request_json(API + "/users;use_login=1/games;game_keys=" + str(game_key) + "/leagues?format=json", token)
        leagues = objects(league_data, "league")
        if not leagues:
            raise ValueError("No Yahoo fantasy football leagues found for this account")
        chosen = None
        for league in leagues:
            if "purvis dudes" in str(first(league, "name", "")).lower():
                chosen = league
                break
        if chosen is None:
            raise ValueError("Purvis Dudes league not found. Available league names are intentionally not logged")
        league_key = first(chosen, "league_key")
        if not league_key:
            raise ValueError("Yahoo league key missing")
        settings = request_json(API + "/league/" + str(league_key) + "/settings?format=json", token)
        standings = request_json(API + "/league/" + str(league_key) + "/standings?format=json", token)
        teams = objects(standings, "team")
        if not teams:
            raise ValueError("Yahoo returned no teams")
        own = [t for t in teams if str(first(t, "is_owned_by_current_login", "0")).lower() in ("1", "true")]
        if len(own) != 1:
            raise ValueError("Unable to identify exactly one Yahoo team owned by the authorized account")
        team_key = first(own[0], "team_key")
        roster_data = request_json(API + "/team/" + str(team_key) + "/roster?format=json", token)
        players = objects(roster_data, "player")
        if not players:
            raise ValueError("Yahoo returned an empty roster")
        scoreboard = request_json(API + "/league/" + str(league_key) + "/scoreboard?format=json", token)
        output = {
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "season": SEASON,
            "league": {
                "league_key": league_key,
                "name": first(chosen, "name"),
                "current_week": first(chosen, "current_week"),
                "scoring_type": first(chosen, "scoring_type"),
                "settings": {
                    "roster_positions": first(settings, "roster_positions"),
                    "stat_categories": first(settings, "stat_categories"),
                    "stat_modifiers": first(settings, "stat_modifiers"),
                },
                "teams": [{
                    "team_key": first(t, "team_key"),
                    "rank": first(t, "rank"),
                    "standings": first(t, "team_standings"),
                    "is_user_team": first(t, "team_key") == team_key,
                } for t in teams],
                "my_team_key": team_key,
                "my_roster": [player_info(p) for p in players],
                "scoreboard": [{
                    "week": first(m, "week"),
                    "status": first(m, "status"),
                    "teams": [{
                        "team_key": first(t, "team_key"),
                        "points": first(t, "team_points"),
                        "projected_points": first(t, "team_projected_points"),
                    } for t in objects(m, "team")],
                } for m in objects(scoreboard, "matchup")],
            },
        }
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print("Yahoo: saved sanitized snapshot with " + str(len(players)) + " rostered players.")
        return 0
    except HTTPError as exc:
        print("Yahoo sync failed: HTTP " + str(exc.code) + " at " + ("token refresh" if "get_token" in exc.url else "fantasy API") + ". No credentials or response bodies logged.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError, KeyError) as exc:
        print("Yahoo sync failed (" + type(exc).__name__ + "): " + (str(exc) if isinstance(exc, ValueError) else "request or response error") + ".", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
