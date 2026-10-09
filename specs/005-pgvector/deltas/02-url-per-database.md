# Delta 02 — one saved URL per database, named automatically

Status: implemented on 2026-10-09, not yet committed. This delta wins over `spec.md` and delta 01 where they differ.

## Why

`spec.md` stored the URL under one name, `pg_url_var`, which defaulted to `HUNCHES_PG_URL` and was edited in a **url var** row. Every pgvector project used the same keyring entry unless the user made up a different name. A second database overwrote the first one's URL, so projects on different databases broke each other. Users had to invent names for these entries and keep track of them.

## Rule

- **Id:** `search.pg_url_id(url)` is the first 16 hex characters of the SHA-256 of `[host lowercased, port (default 5432), database (default: the user), user]`. The URL is parsed with `psycopg.conninfo.conninfo_to_dict`, so both URLs and `key=value` strings work. The id never includes the **password or the query parameters**.
  - So the id is safe to commit, and a password rotation keeps the same id.
  - The same database and user always get the same id, so projects that share a database share one entry automatically.
  - Different hosts, ports, databases or users get different ids, so their entries never overwrite each other.
  - A plain hash rather than an HMAC: the input (host, database, user) is not secret, so a key would protect nothing.
- **Name:** `search.pg_url_name(url_id, url_var)` gives the keyring entry or environment variable that holds the URL:
  1. an explicit `pg_url_var` (a hand-written override, for example for CI);
  2. otherwise `HUNCHES_PG_URL_<ID>` (the id in upper case);
  3. with neither, the old default `HUNCHES_PG_URL`.
  `keys.resolve` checks the environment first, then the keyring, as before. On a headless machine without a keyring, set `HUNCHES_PG_URL_<ID>` in the environment.
- **Config:** a new field, `pg_url_id`. `pg_url_var` stays but is no longer on the form. When a URL is pasted, the form sets `pg_url_id` and clears `pg_url_var`.
- **Unsaved URL for an id:** `pg_connect` raises `The database URL is not saved on this computer: paste it in Project settings (F3), or set HUNCHES_PG_URL_<ID> in the environment`. This is the case for a teammate opening a committed project. With an explicit `pg_url_var` the old message is kept.

## UI (`screens/pg.py`)

- The **url var** row and the **Save URL…** button are removed. The **url** row is a masked input ("paste URL (saved in the keyring)") followed by the status word `env` / `keyring` / `missing` for the name in use.
- `pg_save_url(screen)` runs on **Check store**, **Create** (New project) and **Save** (Project settings). If the box has text, it works out the id, writes the keyring **only if the entry does not already hold that URL**, clears the box and points the form at the id. If the text is not a PostgreSQL URL, or no keyring is available, it shows the reason, nothing else runs, and the error message never repeats the input.
- The current id and any hand-written `pg_url_var` live on the section widget (`PgSection.url_id` and `url_var`), never the URL itself. Project settings loads both from the config.
- A URL is not required to create a project: with none, the project falls back to `HUNCHES_PG_URL`.
- Changing `pg_url_id` (pointing a project at a different database) triggers the existing "re-run Search" consequence in Project settings. Re-pasting the same database with a new password changes nothing in the config.
- Keyring entries are never deleted, because other projects may use them.

## Out of scope

- A picker of already-saved databases in New project. The keyring cannot list its entries, so this would need a list of ids in `system.json`. For now, pasting the same URL again reuses the entry without writing it a second time.

## Tests

- `tests/test_search_pg_connect.py`:
  - the id ignores the password, the query, the host's case and the URL form (URL vs `key=value`);
  - it differs by host, port, database and user, and applies libpq's port and database defaults;
  - bad input is refused without echoing it;
  - the name precedence;
  - `pg_connect` uses the entry for the id over `HUNCHES_PG_URL`, and the not-saved message.
- `tests/test_new_project.py`:
  - two projects on two databases keep two URLs;
  - the status follows the saved URL, and the same URL is not written twice;
  - Check store saves a pasted URL first, and does not run when it cannot save;
  - the password never reaches a file.
- `tests/test_project_settings.py`:
  - pasting a URL in Settings saves it under the id, replaces `pg_url_var`, and asks for confirmation;
  - a project with a saved id shows `keyring`, and re-pasting the same URL is not a change.
