# Working in Docker

One command gives every teammate the same Python 3.12 + uv environment, a running mock service, and (in Compose) Postgres for the copilot store.

```sh
docker compose up -d --build        # builds the image, starts `postgres`, `mock`, then `dev`
docker compose exec dev bash        # your working shell (repo is mounted at /app)
```

Inside that shell, use the commands from `README.md` unchanged:

```sh
uv run --locked python tools/validate_package.py
uv run --locked python -m kyc_copilot.runner.ingest --api-url http://127.0.0.1:8766
uv run --locked python -m unittest -v
uv run --locked python -m kyc_copilot --submit-reviews     # review all cases, submit drafts
uv run --locked python tools/runtime.py pending            # human reviewer commands
```

Or run one-off commands from the host: `docker compose exec dev <command>`.

## How it is set up

| Piece | Detail |
|---|---|
| `mock` container | Runs `tools/runtime.py serve --port 8766`; has a health check on `/health`; **mock bank stays SQLite** (`.state/mock.sqlite`) |
| `postgres` container | `postgres:16-alpine` for the **copilot** knowledge store only. Credentials from `.env.example` (`kyc`/`kyc`). Volume `kyc-postgres` |
| `dev` container | Idle shell that shares the mock's network, so `http://127.0.0.1:8766` works. `KYC_DATABASE_URL` points at `postgres` (`sslmode=disable` — alpine has no TLS) |
| Why shared network | The mock binds to loopback only, as the package requires. It is deliberately not published to the host or network |
| Code | The repo is bind-mounted at `/app`; edit on the host, run in the container |
| State | Mock SQLite in `kyc-state`. Copilot rows in Compose live in `kyc-postgres`. Local/assessor runs without Compose still default to `--db .state/app.sqlite` |
| Python env | Lives in `/opt/venv` in the image, so a host `.venv` never conflicts |

Because the mock is not published, use the container shell (or `docker compose exec dev`) to call it, not `curl` from the host.

## Common tasks

```sh
docker compose logs -f mock          # service output
docker compose restart mock          # restart the service (state survives)
docker compose down                  # stop; named volumes are kept
docker compose down -v               # stop AND delete mock + postgres volumes (fresh run)
docker compose logs -f postgres      # copilot store
docker compose build --no-cache      # rebuild image (after changing pyproject.toml / uv.lock)
```

Reset between independent runs: stop clients, then
`docker compose exec dev uv run --locked python tools/runtime.py reset --confirm`.

## Troubleshooting

- **`mkdir /host_mnt/...: operation not permitted` on macOS.** Docker Desktop is not allowed to read the project folder (common under `~/Downloads`). Move the repo to a normal folder such as `~/projects`, or grant Docker access in System Settings > Privacy & Security > Files and Folders (or Full Disk Access) and restart Docker Desktop.
- **Port 8766 busy.** Not an issue in Docker, since the port is never published; stop any local `runtime.py serve` only if you want to avoid confusion.
- **Dependencies.** Runtime: `pydantic` and `psycopg[binary]` (Postgres store). After changing `pyproject.toml` / `uv.lock`, rebuild. Do not add `requests`, `httpx`, SQLAlchemy, or asyncpg.
- **Compose uses Postgres; host CLI uses SQLite unless you set `KYC_DATABASE_URL` or `--dsn`.** The copilot never opens `.state/mock.sqlite`.
