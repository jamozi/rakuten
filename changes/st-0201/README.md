# ST-0201 local PostgreSQL 18 service

This directory owns the versioned service contract and generated hash inventory
for the ST-0201 local/CI PostgreSQL candidate. The generated Compose file uses
the exact PostgreSQL 18.4 official-image index digest and a file-backed Compose
secret. It is not a production database definition.

## Status boundary

- Local source and generated candidate: `LOCAL_AND_CI_CANDIDATE`
- Docker/Compose runtime on this implementation host: `NOT_EXECUTED`
- Image pull, health probe, and exact server-version assertion: `NOT_EXECUTED`
- Container vulnerability scan: `NOT_EXECUTED`
- Formal TST-008: `NOT_EXECUTED`
- Effective canonical status: unchanged

The local pytest suite proves contract shape, deterministic generation, wrapper
command construction, cleanup behavior, and fail-closed handling. Fake-Docker
tests are not evidence that PostgreSQL ran.

## Files

| Classification      | Path                                                     | Role                                                                                  |
| ------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Source contract     | `changes/st-0201/contracts/local-postgres.v1.yaml`       | Exact image, Compose, runtime, security, and status boundary                          |
| Image snapshot      | `docs/architecture/ST-0201-postgres-image-snapshot.yaml` | Official-source image/index/platform/config metadata checked on 2026-08-02            |
| Generator           | `scripts/build_local_compose.py`                          | Sole cumulative Compose/current-manifest writer; validates ordered Story components    |
| Legacy delegate     | `scripts/build_st0201_postgres_service.py`                | Compatibility entrypoint delegating to the cumulative generator                       |
| Runtime wrapper     | `scripts/postgres_service.sh`                            | Local Docker Compose config/up/check/down and disposable smoke test                   |
| Generated service   | `docker-compose.yml`                                     | Cumulative local stack; the wrapper targets only PostgreSQL in its distinct project   |
| Predecessor inventory | `changes/st-0201/manifest.yaml`                        | Immutable ST-0201 snapshot, pinned by the current Story manifest                      |
| Tests               | `tests/st0201/*.py`                                      | Isolated semantic, adversarial, transaction, fake-Docker, and optional runtime checks |

Do not hand-edit `docker-compose.yml`, and do not regenerate or revise the
immutable `changes/st-0201/manifest.yaml` predecessor snapshot. Change the
owning component contract and run the shared generator.

## Generation

```bash
uv run --locked --no-sync python scripts/build_local_compose.py
uv run --locked --no-sync python scripts/build_local_compose.py --check
```

The shared generator has no Docker, registry, database, or remote mutation operation.
Its `--check` mode is read-only and compares the committed outputs byte for
byte.

## Local operator commands

Supply an exact absolute Docker executable path:

```bash
scripts/postgres_service.sh --docker /absolute/path/to/docker config
scripts/postgres_service.sh --docker /absolute/path/to/docker up
scripts/postgres_service.sh --docker /absolute/path/to/docker check
scripts/postgres_service.sh --docker /absolute/path/to/docker down
scripts/postgres_service.sh --docker /absolute/path/to/docker test
```

For `config`, `up`, `check`, and `down`, the wrapper reads the password from
`${RAOS_POSTGRES_PASSWORD_FILE:-.secrets/postgres_password}`. The file must be
owned by the current user, regular, non-symlinked, mode `0600`, nonempty, and at
most 1024 bytes. The password value is never printed or passed as an argument.
`RAOS_POSTGRES_PORT` defaults to `5432` and must be a
decimal port from 1024 through 65535.

The fixed local Compose project is `raos-st0201-local`. `down` stops that
project but deliberately preserves its named data volume. The `test` command
instead creates a private 0600 ephemeral password, a unique project name, and
a Compose-assigned ephemeral host port; it runs `up --wait --pull always`,
checks health,
asserts the linux/amd64 image config digest and platform, asserts
`SHOW server_version_num;` equals `180004`, and reports PASS only after it has
removed its own project and volume.

Although the installed Compose model also contains later reviewed services,
the ST-0201 wrapper binds the full cumulative file hash and always passes the
explicit `postgres` target. Its project cannot start, stop, or delete the
ST-0202 object-storage container or volume.

The wrapper forces `unix:///var/run/docker.sock`; remote Docker hosts and
contexts are not accepted. It does not support production, remote databases,
raw password environment variables, host networking, privileged mode, Docker
socket mounts, or host data-directory binds.

## Runtime evidence still required

Validation requires a real Docker/Compose execution with immutable logs for
the image pull, healthy container, exact server-version assertion, and cleanup,
plus the required container vulnerability scan. Formal TST-008 additionally
belongs to the canonical CI environment and later database Stories supply its
DDL, extension, seed, constraint, trigger, and role coverage. None of those
formal results are claimed by local generation or fake-Docker tests.
