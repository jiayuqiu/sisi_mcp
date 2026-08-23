# Environment setup prompts

> The project environment file is `./.env` (the repository root), not `~/.env`.
> Never print, paste, or commit real API keys, passwords, or signing secrets.

## 1. Start Dify on port 7080

Use this prompt:

```text
Load `dify/docker/.env` without displaying secret values. Configure the local
Dify instance to use `http://localhost:7080`:

- Set `TRIGGER_URL=http://localhost:7080`.
- Set `EXPOSE_NGINX_PORT=7080`.
- Keep the container-side `NGINX_PORT=80`; only the host-side exposed port changes.
- Do not change unrelated settings or reveal credentials in the response.
```

Start Dify from `dify/docker/`:

```bash
docker compose up -d
```

## 2. Configure the project environment

Set these values in the repository-root `./.env`:

| Parameter | What to set | When it is needed |
|---|---|---|
| `BCI_BASE_URL` | The full BCI API endpoint URL | BCI data sync/backfill |
| `BCI_APP_ID` | BCI-issued application ID | BCI data sync/backfill |
| `BCI_SECRET_KEY` | BCI-issued signing secret | BCI data sync/backfill |
| `DEEPSEEK_API_KEY` | A DeepSeek API key | DeepSeek-backed analysis |
| `SISI_API_KEY` | A SISI API key | SISI model/tool calls |
| `SISI_API_APP_ID` | The SISI application ID | Reserved/configuration metadata; current code does not read it directly |
| `DIFY_API_KEY` | The app API key generated for the imported Dify chatflow, not a console login token | Calling the chatflow |
| `DIFY_CHATFLOW_URL` | `http://localhost:7080/v1` for this local setup, with no trailing slash | Calling the chatflow |

The following settings are only needed for automated Dify workflow deployment:

| Parameter | What to set |
|---|---|
| `DIFY_ADMIN_API_KEY` | The same secret as `ADMIN_API_KEY` in `dify/docker/.env` |
| `DIFY_ADMIN_API_KEY_ENABLE` | Reserved compatibility flag; current project code does not read it |

In `dify/docker/.env`, Dify's actual server settings are named
`ADMIN_API_KEY_ENABLE` and `ADMIN_API_KEY` (without the `DIFY_` prefix). Set
`ADMIN_API_KEY_ENABLE=true` there if automated deployment needs admin-key access.
Keep the admin key private and use a long, randomly generated value.

Generate a new value, for example with `openssl rand -hex 32`, and place the
exact same value in both files using their respective variable names:

`dify/docker/.env`:

```ini
ADMIN_API_KEY_ENABLE=true
ADMIN_API_KEY=<your-new-random-value>
```

Repository-root `./.env`:

```ini
DIFY_ADMIN_API_KEY=<the-exact-same-random-value>
```

Replace the placeholders with the generated value; do not include the `<` or
`>` characters. `DIFY_ADMIN_API_KEY_ENABLE` in `./.env` is currently unused—the
effective enable flag is `ADMIN_API_KEY_ENABLE` in `dify/docker/.env`.

## 3. Replace infrastructure defaults

For anything beyond a disposable local environment, replace the example/default
values in `dify/docker/.env` for:

- `SECRET_KEY`
- `DB_PASSWORD`
- `REDIS_PASSWORD`
- `SANDBOX_API_KEY`
- `PLUGIN_DAEMON_KEY`
- `PLUGIN_DIFY_INNER_API_KEY`

Use independent, randomly generated values. Do not reuse an API key as a database
password or application signing key. Empty public URL settings such as
`CONSOLE_API_URL`, `CONSOLE_WEB_URL`, `SERVICE_API_URL`, `APP_API_URL`,
`APP_WEB_URL`, and `FILES_URL` may remain empty for same-origin local access; set
them to their externally reachable HTTPS URLs when deploying behind a domain or
reverse proxy.

## 4. Validate without exposing secrets

Use this prompt:

```text
Read `./.env` and `dify/docker/.env`, but never output their values. Report each
item only as PASS, MISSING, or MISMATCH:

1. `dify/docker/.env`
   - `TRIGGER_URL` is `http://localhost:7080`.
   - `EXPOSE_NGINX_PORT` is `7080`.
   - Required infrastructure secrets are non-empty and are not example defaults.
   - If admin API access is enabled, `ADMIN_API_KEY` is non-empty.
2. `./.env`
   - Required credentials for the intended workflow are non-empty.
   - `DIFY_CHATFLOW_URL` is `http://localhost:7080/v1`.
   - If automated workflow deployment is used, `DIFY_ADMIN_API_KEY` matches
     Dify's `ADMIN_API_KEY` without displaying either value.
3. Confirm that neither environment file is tracked by Git.
```

## 5. Initialize the SQLite database

The tracked `data/sisi_empty.sqlite` file is the schema-only database template.
If `data/sisi.sqlite` does not exist, create it from the template:

```bash
test -e data/sisi.sqlite || cp data/sisi_empty.sqlite data/sisi.sqlite
```

This command deliberately leaves an existing `data/sisi.sqlite` unchanged. The
backfill workflow will populate the newly created database with source data,
derived results, and worklog records.

Use this prompt:

```text
Check whether `data/sisi.sqlite` exists. If it does not exist, copy
`data/sisi_empty.sqlite` to `data/sisi.sqlite`. Never overwrite an existing
database. Then verify that the new database passes SQLite's integrity check and
contains the expected schema before running backfill.
```

## 6. Finish setup

1. Import the required DSL files into Dify Studio and configure its custom tools
   or MCP servers.
2. Generate the Dify **app API key** for the imported chatflow and put it in
   `DIFY_API_KEY` in `./.env`.
3. Start this project's services from `sisimcp/docker/` with
   `docker compose up -d`.
4. Run the backfill workflow, adjusting dates as needed:

   ```bash
   uv run python mcp_conductor/entry/main_backfill.py \
     --start-date 2026-06-29 \
     --end-date 2026-07-08 \
     --sleep 1 \
     --require-sync-data
   ```
