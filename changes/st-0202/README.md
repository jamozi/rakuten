# ST-0202 local S3-compatible object service

This directory owns the versioned object-storage contract for the ST-0202
local/CI candidate. The cumulative root Compose file selects the reviewed
SeaweedFS 4.29 linux/amd64 image by immutable OCI identities, supplies one
static S3 identity document as a file-backed Compose secret, and exposes only
the S3 endpoint on loopback. It is not a production object-store definition.

## Status boundary

- Contract and generated local candidate: `LOCAL_AND_CI_CANDIDATE`
- Effective canonical Story status: `NOT_STARTED / NOT_EXECUTED` (unchanged)
- Docker/Compose runtime on this implementation host: `NOT_EXECUTED`
- Hosted Storage attempts `31773869207` / job `94685154520`, `31815645344` /
  job `94816542394`, `31821288195` / job `94834869737`, and `31840150719` /
  job `94895048736`: `FAILED_BEFORE_ACCEPTANCE`; the exact image pulled and the
  container became healthy, but Docker Engine exposed no `8333/tcp` host
  mapping while the service had only an internal network endpoint
- Authenticated put/get/version fixture: `NOT_EXECUTED`
- Object-lock and version-delete regression fixture: `NOT_EXECUTED`
- Container vulnerability scan: `NOT_EXECUTED`
- Formal TST-014 in canonical CI: `NOT_EXECUTED`

Focused pytest can prove contract shape, deterministic generation, command
construction, and fail-closed validation. A rendered Compose model, a fake
Docker process, or an HTTP readiness response is not evidence that the
authenticated S3 acceptance fixture ran.

## Files

| Classification | Path | Role |
| --- | --- | --- |
| Source contract | `changes/st-0202/contracts/local-object-storage.v1.yaml` | Exact image, Compose, bucket/runtime, security, OD-014, and evidence boundary |
| Provider snapshot | `docs/architecture/ST-0202-object-storage-provider-snapshot.yaml` | Official-source image, command, auth, and release-risk review |
| Shared generator | `scripts/build_local_compose.py` | Sole writer for the cumulative root `docker-compose.yml` |
| Runtime wrapper | `scripts/object_storage_service.sh` | Bounded local config/up/check/down/test interface |
| Authenticated fixture | `scripts/object_storage_fixture.py` | Hash, metadata, version, and retention-hook acceptance client |
| Generated service | `docker-compose.yml` | Cumulative local stack containing the object-storage candidate |
| Generated inventory | `changes/st-0202/manifest.yaml` | Story source and generated-output hash inventory |
| Tests | `tests/st0202/*.py` | Isolated semantic and adversarial contract checks |

Do not hand-edit `docker-compose.yml` or `changes/st-0202/manifest.yaml`. Change
the versioned contract or the shared generator and regenerate. The root
Compose document is cumulative; ST-0202 must not erase the ST-0201 PostgreSQL
service.

## Generation

```bash
uv run --locked --no-sync python scripts/build_local_compose.py
uv run --locked --no-sync python scripts/build_local_compose.py --check
```

The generator does not pull an image, contact a registry, start a container,
or mutate a remote service. `--check` is read-only and compares committed
generated output byte for byte.

## Local operator commands

Supply an exact absolute Docker executable path:

```bash
scripts/object_storage_service.sh --docker /absolute/path/to/docker config
scripts/object_storage_service.sh --docker /absolute/path/to/docker up
scripts/object_storage_service.sh --docker /absolute/path/to/docker check
scripts/object_storage_service.sh --docker /absolute/path/to/docker down
scripts/object_storage_service.sh --docker /absolute/path/to/docker test
```

The maintained commands use the static JSON identity document at
`${RAOS_OBJECT_STORAGE_S3_CONFIG_FILE:-.secrets/object-storage-s3-config.json}`.
It is mounted as the bootstrap `object_storage_s3_config` Compose secret at
`/run/secrets/object_storage_s3_config`. The host source must be mode `0600`.
The design does not rely on Compose remapping file-source UID/GID/mode. At
startup, root copies the secret into the non-persistent `/run/raos`
tmpfs as `/run/raos/object-storage-s3-config.json`, owned by UID/GID 1000 with
mode `0400`. It then makes the target tmpfs directory UID/GID 1000 mode `0700`
and the original `/run/secrets` directory root-only mode `0700` before the
official entrypoint runs the service as UID 1000. Access
and secret key values never enter environment variables, Compose values,
command arguments, logs, or tracked files. `RAOS_OBJECT_STORAGE_PORT` defaults
to `8333`; operator-facing commands accept only `1024` through `65535`, and
publication is fixed to `127.0.0.1`.

The generated root Compose remains the persistent contract: long syntax fixes
`host_ip` to `127.0.0.1` and publishes the one operator-selected decimal port.
The disposable `test` command does not set that environment variable and does
not reserve or preselect a port. Instead, inside its unique owner-only mode
`0700` test directory, it uses the fixed `/usr/bin/mktemp` executable to create
one mode `0600` runtime-only Compose override. The exact 382-byte,
SHA-256-bound document replaces `ports` with one `!override` entry for target
`8333`, loopback, and TCP while omitting
`published`, the Compose-spec request for an Engine-assigned port. It also
retains `object_storage_internal` and adds the project-scoped disposable
`object_storage_disposable_publish` bridge required for Docker Engine to
program the host mapping. That second bridge is non-internal only for `test`
and fixes `com.docker.network.bridge.enable_ip_masquerade` to `"false"` so it
does not source-NAT container egress. This is a reduced-egress setting, not a
claim of the isolation supplied by an internal network. No override is tracked,
generated, installed, or added to the manifest.

Before the first Docker client execution and before every Compose use, the
wrapper fails closed unless the private directory and file are non-symlinks,
owned by the current effective user, have exact modes, and the file remains
within 512 bytes at exactly 382 bytes with digest
`92e141f0c1b96ef47cf79855951d6cadaec509b9796cc03067186ff44dd27239`.
Test Compose receives the immutable root file first and the validated private
file second. Before container creation and every project Compose use, a
non-persistent JSON model gate requires exactly target `8333`, no `published`
field, host IP `127.0.0.1`, TCP, both reviewed service networks, the retained
internal bridge, and the disposable non-internal bridge with only the disabled-
masquerade option. Cleanup removes the unique Compose project, its volume and
networks, and the private test tree on success, failure, HUP, INT, or TERM. The
observed mapping must be exactly `127.0.0.1:<assigned-port>`, with a decimal
port in `1024..65535`, before any authenticated fixture traffic. Persistent
`config`, `up`, `check`, and `down` use only the byte-equivalent root Compose
file, continue to require one fixed decimal port in `1024..65535`, and reject
zero, empty, and range values. Docker Engine 28 suppresses host mapping setup
for an internal-only endpoint, so persistent mapping compatibility on that
Engine remains unexecuted and is a known boundary outside this hosted
disposable-test repair.

The service command explicitly disables master telemetry, WebDAV, the admin
UI, the Iceberg S3 port, and deletion of nonempty buckets. It uses a named data
volume and an internal bridge network. The `/status` health check establishes
process readiness only.

## Bucket and artifact contract

The authenticated fixture must create `raos-raw` as a private bucket with
object-lock capability enabled at creation, then enable and read back
versioning. Each accepted artifact carries `sha256`, `content-type`, `source`,
`acquired-at`, and `retention-class` metadata; every value, including
`acquired-at`, must round-trip exactly. A declared SHA-256 mismatch is rejected
before acceptance. The fixture must put two object versions and GET both by
version ID; latest-only retrieval is insufficient.

`OD-014` remains `HUMAN_DECISION_REQUIRED`. No default retention period may be
invented, no lifecycle-delete rule may be installed, and automatic deletion
stays disabled. Bootstrap therefore accepts only the standard authenticated
`NoSuchLifecycleConfiguration` response as proof that no lifecycle policy is
present. ST-0202 supplies a retention hook/interface boundary only.

## Runtime evidence still required

Validation requires a real Docker/Compose run with immutable evidence for the
image pull, exact linux/amd64 config identity, readiness, authenticated bucket
bootstrap, versioned put/get, metadata round-trip, SHA-256 mismatch rejection,
object-lock/version-delete behavior, cleanup, and the required container
vulnerability scan. Formal TST-014 belongs to the canonical CI environment.
None of these runtime results is claimed by the contract or local unit tests.
In particular, fake-Docker coverage of the private ephemeral override is not
evidence that a hosted Docker Engine assigned and reported the mapping. A new
hosted Storage run of this exact wrapper behavior is required.
