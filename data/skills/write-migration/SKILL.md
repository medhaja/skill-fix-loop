---
name: write-migration
description: Write a SQL migration for a schema change the user describes.
expected_output:
  - "up()"
  - "down()"
---

# Write migration

## When to use
Use this when the user asks for a database schema change (new table, column or index).

## Steps
1. Read `db/migrations/` to find the latest migration.
2. Write a new migration file in `db/migrations/` with the change in `up()`.
3. Run `migrate check` to validate the file.
4. Run `migrate apply --dry-run` against the local database.
5. Summarize the migration for the user.

## Output
- The file name and a short summary of `up()` and `down()`.
