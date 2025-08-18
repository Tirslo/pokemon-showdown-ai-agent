# Pokemon Showdown AI Agent

## Install

```bash
uv venv --python 3.13
source .venv/bin/activate
uv sync
```

## Pre-requisite

Run Pokemon Showdown server

```bash
git clone https://github.com/smogon/pokemon-showdown
cd pokemon-showdown
git checkout v0.11.10 # Important. Using master doesn't work
npm ci
npm start
```

## Run

Sign in using `human_player1` in Pokemon Showdown. Import a Gen1 team using [human_team.txt](human_team.txt). Start agent

```bash
aws sso login
python agent.py
```
