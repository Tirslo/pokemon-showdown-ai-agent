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

## Set AWS_PROFILE

If not using the default profile boto3 can use env var `AWS_PROFILE`

```bash
alias aws-login-dev='aws sso login --profile <profile name> && export AWS_PROFILE=<profile name>'
```

## Set MongoDB URI for memory 

```bash
export MONGO_URI="mongo+srv://username:password@host.mongodb.net/?appName=myapp"
```

## Run

Sign in using `human_player1` in Pokemon Showdown. Import a Gen1 team using [human_team.txt](human_team.txt). Start agent

```bash
aws sso login
python agent.py
```
