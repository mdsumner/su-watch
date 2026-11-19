# SU watch

A daily page of Service Unit (SU) budgets and burn for the
[Nectar Research Cloud](https://ardc.edu.au/services/ardc-nectar-research-cloud/) projects I
belong to: <https://mdsumner.github.io/su-watch/>

Why: shut-off and suspended VMs are charged in full. Only shelving or deleting a VM stops
the charge ([Nectar: Service Units](https://support.ehelp.edu.au/support/solutions/articles/6000257023)).
In November 2026, two VMs that had been stopped since August used two-thirds of one project's yearly
budget, and nothing in the dashboard made that obvious.

## What it shows, and where the numbers come from

| | Source |
|---|---|
| Budget | `rating.budget` of the project's current approved allocation (Allocations API) |
| Used | SU charged since that allocation started (Rating service, `openstack rating summary get`) |
| What used it | the same, grouped by VM (`-g id`); deleted VMs keep their charges but lose their names |
| Burn now | the flavour rate (`nectar:rate`, SU/hour) of every VM that exists, shelved ones excepted |
| Charged, last 7 days | Rating, last 7 days; it includes old flavours with no published rate |
| Runs out | when the budget is used up at today's burn |

It publishes project names, VM names, flavours, states and SU. It leaves out IPs, IDs,
emails and people's names.

## How it runs

`collector/` runs on a machine that holds OpenStack credentials (one OpenStack password
works for every project you belong to; each call is scoped to one project):

- `su-watch.sh` loads the credentials and runs `su_watch.py`, which writes JSON to stdout (read-only).
- `publish.sh` writes `data/su-watch.json`, appends to `data/history.csv`, and commits and pushes.
- `su-watch.service` + `su-watch.timer`: a systemd user timer, daily at 20:00 UTC.

```bash
mkdir -p ~/.config/systemd/user
cp collector/su-watch.service collector/su-watch.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now su-watch.timer
systemctl --user list-timers su-watch.timer     # next run
journalctl --user -u su-watch.service           # last runs
```

Needs `python-openstackclient` and `python-cloudkittyclient` (in `~/venvs/openstack`), the RC
file and password file in `~/.nec/`, and a git credential that can push to this repo.

The page (`index.html`) is static and reads `data/su-watch.json`. It shows a warning if the
data is more than 36 hours old.
