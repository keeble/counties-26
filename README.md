# County Championships 2026 — Bowling Scorer

Local scoring tool for a round-robin ten-pin bowling tournament using Petersen-style points.
Imports the organizer-supplied lane draw, then imports lane-software score exports after each
round, computes standings, and builds a static site for publishing to GitHub Pages.

## Scoring rules

- Round-robin, one game per team pairing.
- Positional 1v1 matchups (bowler vs their opposite number on the other team) are worth 10 bonus
  points each, split 5/5 on a tie.
- The team with the higher total pinfall for the match also gets a team bonus (40 for women's
  4-a-side, 50 for men's 5-a-side), split evenly on a tie.
- A team's match total = sum of bowler scratch scores + individual bonuses won + team bonus.

## Usage

```bash
pip install -e ".[test]"

# One-time: import the draw for each division
counties26 import-draw men_draw.csv men_teams.csv --players men_players.csv --division men
counties26 import-draw women_draw.csv women_teams.csv --players women_players.csv --division women

# Add a centre-export abbreviation for a registered player
counties26 add-alias "Laura M" --division women --team-number 15 \
  --player "Laura Morgan"

# After each tournament game is bowled. `--round` is the tournament game/fixture;
# `--game` selects that game within the centre's cumulative export block.
counties26 import scores.csv --round 4 --game 1 --division men \
  --unknown-aliases unknown_players.csv

# After editing unknown_players.csv to fill in player_name values
counties26 add-aliases unknown_players.csv

# Anytime
counties26 show-standings --division men
counties26 build-site --output docs
```

## Development

Known centre-export names and abbreviations are resolved automatically using the
registered roster and aliases. Matching tries known aliases, a unique first name,
a unique first name plus second-name initial, then a unique surname. Unknown or
ambiguous names are reported and excluded when a team roster exists, rather than
guessed. `--unknown-aliases` writes those names to an editable CSV.

```bash
pytest
```
