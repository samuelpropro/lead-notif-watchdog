"""Lead notification watchdog.

For each client: read the leads Sheet; any lead younger than MAX_AGE_H and older
than GRACE_MIN whose phone number is not on the client's ntfy topic gets its
notification resent (client's own template). Stateless: a resent message contains
the phone, so the next run sees it. Config comes from the CLIENTS_JSON env var.
"""
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

PARIS = ZoneInfo("Europe/Paris")
GRACE_MIN = 3
MAX_AGE_H = 11  # ntfy.sh keeps messages ~12h
DRY = "--dry" in sys.argv


def log(*a):
    print(dt.datetime.now(PARIS).strftime("%d/%m %H:%M:%S"), *a, flush=True)


def token():
    info = json.loads(os.environ["GOOGLE_SA_JSON"])
    c = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    c.refresh(Request())
    return c.token


def rows(tok, sheet, rng):
    r = requests.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet}/values/{rng}",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    r.raise_for_status()
    return [x + [""] * (40 - len(x)) for x in r.json().get("values", [])]


def topic_text(topic):
    r = requests.get(f"{topic}/json?poll=1&since=12h", timeout=30)
    r.raise_for_status()
    return " ".join(json.loads(l).get("message", "") for l in r.text.splitlines() if l.strip())


def fill(tpl, row):
    """Replace {N} with column N of the row (0 = column A)."""
    return re.sub(r"\{(\d+)\}", lambda m: row[int(m.group(1))].strip(), tpl)


def check(client, tok, now):
    name = client["name"]
    text = None
    missing = 0
    for x in rows(tok, client["sheet"], client["range"]):
        try:
            t = dt.datetime.strptime(x[client["date_col"]], "%d/%m/%Y %H:%M").replace(tzinfo=PARIS)
        except ValueError:
            continue  # header / template line
        age = (now - t).total_seconds() / 60
        phone = x[client["phone_col"]].strip()
        if not phone or age < GRACE_MIN or age > MAX_AGE_H * 60:
            continue
        if text is None:
            text = topic_text(client["topic"])
        if phone in text:
            continue
        missing += 1
        body = fill(client["template"], x)
        actions = fill(client["actions"], x)
        log(name, "MISSING -> resend", x[client["name_col"]])
        if DRY:
            continue
        r = requests.post(client["topic"], data=body.encode(), params={"actions": actions}, timeout=30,
                          headers={"Title": client["title"], "Priority": "high", "Tags": client["tags"]})
        log(name, "ntfy", r.status_code)
        if not r.ok:
            raise RuntimeError(f"{name}: ntfy {r.status_code} {r.text[:200]}")
    log(name, "ok" if not missing else f"{missing} resent")


def main():
    clients = json.loads(os.environ["CLIENTS_JSON"])
    tok = token()
    now = dt.datetime.now(PARIS)
    errors = []
    for c in clients:
        try:
            check(c, tok, now)
        except Exception as e:  # one client failing must not block the others
            errors.append(f"{c['name']}: {e}")
            log("ERROR", c["name"], e)
    if errors:
        sys.exit(1)  # red run -> GitHub emails the owner


if __name__ == "__main__":
    main()
