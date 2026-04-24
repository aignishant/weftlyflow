# Execution data storage

Each workflow run produces two kinds of state:

- **Execution metadata** — id, status, timings, mode, who triggered it.
  This row is small, indexed, and listed all the time (the executions
  page, the `wait_till` scheduler, the audit trail). It always lives in
  Postgres.
- **Execution payload** — the immutable workflow snapshot plus the
  per-node `run_data` tree (every item every node produced). This can be
  *large* — one execution of an HTTP workflow with image responses can
  easily push past a megabyte; a noisy customer can fill gigabytes in a
  day. Where this payload physically lives is pluggable.

## Backends

The backend is chosen by `WEFTLYFLOW_EXECUTION_DATA_BACKEND`.

### `db` (default)

Payload is inlined into the `execution_data.workflow_snapshot` +
`execution_data.run_data` JSON columns.

**Use when:**

- Total retention × average payload size fits comfortably inside your
  Postgres instance.
- You want a single backup to cover everything.
- Simplicity matters more than cost.

**Watch for:**

- Table bloat in autovacuum output.
- Slow `VACUUM` / dump times once the table crosses tens of GB.

### `fs`

Payload is written as one JSON file per execution under a base path:

```
<base>/<yyyy>/<mm>/<execution_id>.json
```

The DB row still exists — `storage_kind='fs'`, `external_ref` points at
the blob — but the `workflow_snapshot` and `run_data` columns are empty
`{}`. Writes are atomic on POSIX via `tempfile + rename`.

**Use when:**

- You want Postgres to stay lean and don't mind a second storage class.
- You already back up a host/volume mount and want to layer a retention
  sweep on top of it (cron `find /var/lib/weftlyflow/exec -mtime +30 -delete`).
- You plan to tier cold payloads onto cheaper storage out of band.

**Required settings:**

```bash
WEFTLYFLOW_EXECUTION_DATA_BACKEND=fs
WEFTLYFLOW_EXECUTION_DATA_FS_PATH=/var/lib/weftlyflow/exec
```

The base path is created on first write. Every API pod *and* every Celery
worker must see the same path — mount a shared volume (NFS, EFS, Longhorn,
CephFS) when running more than one replica. A per-pod volume will silently
lose payloads the moment an execution moves between pods.

**Permissions:** the process user needs read/write on the base path. In
Kubernetes set `securityContext.fsGroup` to match.

## Switching backends

Switching from `db` → `fs` applies only to *new* executions. Existing
rows keep their inline payload and are still readable — the store
interrogates each row's `storage_kind` before deciding how to read it.
You can leave historical rows alone or migrate them manually with a
small script that loads each row, calls
`FilesystemExecutionDataStore.write()`, and clears the JSON columns.

Switching from `fs` → `db` is safe for new executions but **leaves old
files on disk** — the store's `delete` method runs on row deletion
(cascade from `executions`), not on backend change. Clean up the base
path manually once old runs are expired.

## Retention

Weftlyflow does not expire executions out of the box. Options:

- **DB sweep.** Delete old `executions` rows via a cron job:

  ```sql
  DELETE FROM executions WHERE started_at < NOW() - INTERVAL '30 days';
  ```

  The `execution_data` row is removed via `ON DELETE CASCADE`. For the
  `fs` backend the blob on disk is **not** touched — pair the SQL sweep
  with a `find` command.

- **Filesystem sweep.** If on `fs`, age out files directly and let them
  become dangling references. The `get()` call will return a read error
  for deleted files; handle the exception in your own UI if you expose
  the execution detail to end users.

## Backups

- **`db` backend** — included in the regular Postgres dump; no extra
  steps.
- **`fs` backend** — back up the volume at the same cadence as the DB.
  Mismatched restore points leave the DB pointing at files that aren't
  there; restore both together or accept the dangling references.

## S3 and object-store backends

`S3ExecutionDataStore` is not yet implemented. The `ExecutionDataStore`
protocol (see `weftlyflow.db.execution_storage`) is stable — a custom
backend implements three async methods and is injected into
`ExecutionRepository(data_store=...)` or registered via
`set_default_store()`. Community contributions welcome.

### Implementation sketch

The filesystem backend is the closest analogue. An S3 backend should:

1. Take the same "shard by year/month" key layout — e.g.
   `<prefix>/<yyyy>/<mm>/<execution_id>.json`. Year/month grouping
   keeps lifecycle rules simple (`lifecycle.Expiration` on a prefix
   with a `/2025/09/` filter).
2. Use `aioboto3` or wrap `boto3` in `asyncio.to_thread` the same way
   `AWSSecretsManagerProvider` already does. Do **not** spin the sync
   client on every call — cache a session per provider instance.
3. Write with `PutObject` and `ContentType: application/json`. Reads
   go through `GetObject` + `.read()`. Deletes via `DeleteObject`;
   swallow 404 the same way the FS store ignores
   `FileNotFoundError`.
4. Store `external_ref` as the full S3 URI
   (`s3://<bucket>/<key>`), not just the key — the URI is
   self-describing across bucket renames.
5. Required settings (mirror the FS pattern):
   - `execution_data_s3_bucket`
   - `execution_data_s3_prefix` (default `weftlyflow/exec`)
   - `execution_data_s3_region`
   - `execution_data_s3_endpoint_url` — optional, for S3-compatible
     object stores (MinIO, R2, Wasabi).
   - Credentials follow the usual boto3 chain (env, instance
     profile, `~/.aws/credentials`); no special handling needed.
6. Ship behind a new `s3` optional extra:
   ```toml
   s3 = ["aioboto3>=12.0"]
   ```
   Import `aioboto3` lazily inside the store module so the default
   install stays dependency-free.
7. Tests belong under `tests/unit/db/test_execution_storage_s3.py`,
   using [moto](https://github.com/getmoto/moto)
   (`@mock_aws` decorator) to stub S3 — no live AWS calls in CI.

### When to build it

Trigger conditions:

- A deployment crosses ~100 GB of execution payload and wants to
  tier to a cheaper storage class than Postgres or local disk.
- A multi-region deployment needs payload access from pods in a
  different AZ than the FS volume lives in.

Until one of those fires, `fs` backend with a shared volume (EFS,
Longhorn, CephFS) is sufficient and simpler to operate. The `fs`
backend has been load-tested up to ~500 GB with no operational
issues.
