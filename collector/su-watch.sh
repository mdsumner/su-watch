#!/usr/bin/env bash
# Collect SU budget/use/burn for all your Nectar projects as JSON on stdout.
# Credentials: the ACE_eco_stats RC file + password file (the password works for every
# project you belong to). Prints nothing secret.
set -euo pipefail
source ~/.nec/ACE_eco_stats-openrc.sh < ~/.nec/pw > /dev/null 2>&1
exec ~/venvs/openstack/bin/python "$(dirname "$0")/su_watch.py"
