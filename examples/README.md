# Dummy run

Run these commands from the repository root. The database is disposable, so remove it and repeat the commands whenever you want a clean run.

```bash
rm -f examples/dummy.db

counties26 import-draw examples/men_grid.csv examples/men_teams.csv \
  --players examples/men_players.csv --division men --db examples/dummy.db
counties26 import-draw examples/women_grid.csv examples/women_teams.csv \
  --players examples/women_players.csv --division women --db examples/dummy.db

counties26 import examples/men_scores_round1.csv \
  --round 1 --game 1 --division men --db examples/dummy.db --yes
counties26 import examples/women_scores_round1.csv \
  --round 1 --game 1 --division women --db examples/dummy.db --yes

counties26 show-standings --division men --db examples/dummy.db
counties26 show-standings --division women --db examples/dummy.db
counties26 build-site --db examples/dummy.db --output examples/site
```

The grids contain four teams and three rounds. The score files contain round 1 only;
the `--game 1` value demonstrates the centre game-in-block argument. The simplified
example score files do not include a `Game number` column, so the option is ignored for
them. The original centre export does include that column and will be filtered by it.
Each score file has the correct lineup size, so the import should report no warnings.
Re-run either import command to see duplicate detection.

To teach the importer a known centre abbreviation, add it once after importing
the roster:

```bash
counties26 add-alias "Alex M" --division men --team-number 1 \
  --player "Alex Morgan" --db examples/dummy.db
```

Future score imports automatically resolve `Alex M` to `Alex Morgan`; no mapping
file is required. Unknown names are highlighted and excluded when a team roster
exists.

For unknown names, ask the importer to create an editable alias file:

```bash
counties26 import scores.csv --round 1 --game 1 --division men \
  --unknown-aliases unknown_players.csv --db examples/dummy.db
# Fill in the player_name column, then:
counties26 add-aliases unknown_players.csv --db examples/dummy.db
```

The player registry files use this format:

```text
team_number,play_position,player_name
1,1,Alex Morgan
```

The roster is imported with the draw and appears on each team's page. The centre
export remains the source of the names attached to actual scores, which allows
substitutes to be recorded when necessary.

Add a known centre abbreviation once, after importing the roster:

```bash
counties26 add-alias "Alex M" --division men --team-number 1 \
  --player "Alex Morgan" --db examples/dummy.db
```
