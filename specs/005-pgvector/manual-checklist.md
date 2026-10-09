# 005 pgvector: managed-service manual checklist

Everything here is **needs a human**. Nothing was run by an agent (no AWS account, no managed database, no network to them), and no box is ticked. Run it once per service (RDS, Aurora, Supabase, other) and once more for each pooler URL the service offers. Record the date, service, engine and pgvector version next to each item.

Setup for every item: a small embedded table you can read (a few hundred rows is enough), a project whose `.hunches/config.toml` has `backend = "pgvector"`, `pg_table`, the column names, and an `embedding_model` that matches the table. The URL goes in the environment variable named by `pg_url_var` (default `HUNCHES_PG_URL`) or in the keyring (New project: Save URL). Never in `config.toml`.

## A. Any service, URL authentication (`pg_auth = "url"`)

- [ ] **needs a human** A1. New project, backend PostgreSQL, Check store. Expect: pgvector version, the extension's schema, the column type and dimension, a row estimate, the index list, a one-row sample. Compare each with `psql`.
- [ ] **needs a human** A2. Check store encryption line. With `?sslmode=require` expect encrypted; without it note what the service does by default.
- [ ] **needs a human** A3. Stage 2 Search, `pg_search = "exact"`, a few seeds. Expect candidates equal to what you get by running the same query by hand, and no APPROXIMATE banner.
- [ ] **needs a human** A4. Set `pg_statement_timeout_s = 1` (or lower the role's `statement_timeout`) on a table big enough to exceed it, then Search. Expect Postgres's `canceling statement due to statement timeout` followed by `Fix: raise statement_timeout for this role, or set pg_statement_timeout_s in config.toml`. Then set `pg_statement_timeout_s = 0` and check the search is no longer cut off.
- [ ] **needs a human** A5. Press Stop (`x`) during a long exact search. Expect `Search stopped.`, and on the server no query left running (`select * from pg_stat_activity where state = 'active'`).
- [ ] **needs a human** A6. A wrong password or a URL with a typo. Expect the driver's message, with the URL and password replaced by `***`; grep the screen and `.hunches/` for the password.
- [ ] **needs a human** A7. `pg_search = "index"` on a server below pgvector 0.8.0. Expect `pg_search = "index" needs pgvector 0.8.0 or newer (found X)...` before any query. On 0.8.0+ with an HNSW `vector_cosine_ops` index, expect the permanent APPROXIMATE banner.
- [ ] **needs a human** A8. A table whose vector column is `halfvec`, and (Supabase) the extension in schema `extensions`. Expect Check store and Search to work.
- [ ] **needs a human** A9. A read replica or Aurora reader endpoint, with a search long enough to be cancelled by replication. Expect Postgres's `conflict with recovery` text plus the `Fix: run the search against the primary/writer endpoint...` hint. (Only if you can provoke it.)

## B. Poolers (Supabase port 6543 transaction mode, PgBouncer, RDS Proxy)

- [ ] **needs a human** B1. Check store through the transaction-pooler URL. Expect the note that the URL looks like a transaction pooler.
- [ ] **needs a human** B2. An exact search through the pooler URL on a small table. Expect it to work (hunches opens the connection with `prepare_threshold=None` and runs everything in one transaction). If it fails, record the message.
- [ ] **needs a human** B3. The same search through the direct or session-mode URL for comparison. Record whether `pg_statement_timeout_s` (a `SET LOCAL`) is honoured through the pooler (A4 on both URLs).

## C. RDS / Aurora IAM database authentication (`pg_auth = "rds_iam"`)

Facts below are from the AWS RDS User Guide pages "IAM database authentication", "Creating and using an IAM policy for IAM database access", "Creating a database account using IAM authentication" and "Troubleshooting for IAM DB authentication" (read 2026-10-09). Re-read them if a step differs.

### C.1 One-time setup

- [ ] **needs a human** C1. IAM database authentication is enabled on the instance or cluster (the CLI flag is `--enable-iam-database-authentication`; console: modify the DB instance). The guide notes IAM DB authentication needs 300 to 1000 MiB of extra memory on the database.
- [ ] **needs a human** C2. Find the resource id. For an RDS instance: `aws rds describe-db-instances --query "DBInstances[*].[DBInstanceIdentifier,DbiResourceId]"` (console: the instance, Configuration tab, Resource ID, looks like `db-ABCDEFGHIJKL01234`). For Aurora use the cluster's `DbClusterResourceId`. Through RDS Proxy use the proxy's resource id (`prx-...`). The id is unique to a Region and never changes.
- [ ] **needs a human** C3. Create an IAM policy and attach it to the role or user hunches will run as:

  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": ["rds-db:connect"],
        "Resource": ["arn:aws:rds-db:<region>:<account-id>:dbuser:<DbiResourceId>/<db_user>"]
      }
    ]
  }
  ```

  The ARN names one database account in one instance. The IAM identity must be in the same account as the instance (cross-account: assume a role in the instance's account). The database user name is case-sensitive and must match the one in the ARN. An administrator can connect without this policy.
- [ ] **needs a human** C4. In the database, as the master user or another user who can create users:

  ```sql
  CREATE USER db_user;
  GRANT rds_iam TO db_user;
  GRANT CONNECT ON DATABASE mydb TO db_user;      -- as your setup needs
  GRANT USAGE ON SCHEMA public TO db_user;
  GRANT SELECT ON public.docs TO db_user;         -- hunches only ever SELECTs
  ```

  Nested or indirect grants of `rds_iam` also work. Once `rds_iam` is granted, that user logs in only with IAM (it takes precedence over a password, per the guide).
- [ ] **needs a human** C5. Get the TLS bundle for `sslmode=verify-full` (optional; the default below uses `require`).

### C.2 Configure hunches

- [ ] **needs a human** C6. In `config.toml`: `pg_auth = "rds_iam"`, optionally `pg_aws_region` and `pg_aws_profile` (otherwise boto3's default region and credential chain). Install with `pip install "hunches[rds]"`.
- [ ] **needs a human** C7. Set the URL variable to a URL **without a password** and with the real instance endpoint as host (not a Route 53 alias, which cannot be used to generate the token):

  ```
  postgresql://db_user@my-instance.abc123.us-east-1.rds.amazonaws.com:5432/mydb?sslmode=verify-full&sslrootcert=/path/global-bundle.pem
  ```

  If the URL has no `sslmode`, hunches adds `sslmode=require`.

### C.3 Expected results

- [ ] **needs a human** C8. Success: Check store shows the version, column and sample as in A1, and encrypted. Search works. A search longer than 15 minutes is unaffected, because the token (valid 15 minutes) is only used to authenticate and does not affect the session afterwards; each search generates a fresh one.
- [ ] **needs a human** C9. No AWS credentials: expect `AWS: <botocore message>`.
- [ ] **needs a human** C10. No region anywhere: expect `pg_aws_region is not set and boto3 found no default region`.
- [ ] **needs a human** C11. boto3 missing (install only `hunches[pg]`): expect `IAM authentication needs boto3: pip install hunches[rds]`.
- [ ] **needs a human** C12. Remove the `rds-db:connect` permission (or use a different db user in the ARN). Expect the server's authentication message followed by `Check: the database user has the rds_iam role, the AWS identity may rds-db:connect on this DbiResourceId/user, and the URL host is the instance endpoint (not a custom DNS name).` The AWS guide lists the server-side text for this case as `Failed to authorize the connection request for user ... is not authorized to perform rds-db:connect` (error code `NotAuthorized`); **record the exact text you see and whether it contains "authentication failed"**, because the hint is attached only when it does (spec, task 02: that wording is unverified).
- [ ] **needs a human** C13. Revoke `rds_iam` from the user. Record the message and whether the `Check:` line appears.
- [ ] **needs a human** C14. Use a custom DNS name as the host. Record the message and whether the `Check:` line appears.
- [ ] **needs a human** C15. Grep the screen, `config.toml`, `system.json`, `.hunches/` for the generated token and the URL: none may appear in any error.
- [ ] **needs a human** C16. If you use RDS Proxy: repeat C8 with the proxy endpoint and the `prx-...` resource id in the policy.
