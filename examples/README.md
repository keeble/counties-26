# Dummy run

Run these commands from the repository root. The database is disposable, so remove it and repeat the commands whenever you want a clean run.

```bash
rm -f examples/dummy.db

counties26 import-draw examples/men_grid.csv examples/men_teams.csv \
  --division men --db examples/dummy.db
counties26 import-draw examples/women_grid.csv examples/women_teams.csv \
  --division women --db examples/dummy.db

counties26 import examples/men_scores_round1.csv \
  --round 1 --division men --db examples/dummy.db --yes
counties26 import examples/women_scores_round1.csv \
  --round 1 --division women --db examples/dummy.db --yes

counties26 show-standings --division men --db examples/dummy.db
counties26 show-standings --division women --db examples/dummy.db
counties26 build-site --db examples/dummy.db --output examples/site
```

The grids contain four teams and three rounds. The score files contain round 1 only.
Each score file has the correct lineup size, so the import should report no warnings.
Re-run either import command to see duplicate detection.
