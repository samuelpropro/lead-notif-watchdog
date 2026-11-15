# lead-notif-watchdog

Every 30 min (GitHub Actions): for each client, any lead in the leads Sheet that is
missing from the client's ntfy topic gets its notification resent.

Secrets:
- `GOOGLE_SA_JSON`: Google service account key (read access to the Sheets).
- `CLIENTS_JSON`: list of clients — `name, sheet, range, topic, title, tags,
  date_col, phone_col, name_col, template, actions` (template uses `{column index}`).

Run locally: `GOOGLE_SA_JSON=... CLIENTS_JSON=... python watchdog.py --dry`
