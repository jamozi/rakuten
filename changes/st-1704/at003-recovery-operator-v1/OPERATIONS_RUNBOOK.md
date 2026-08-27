# AT-003 Draft recovery operations

1. Build and check the deterministic package:

   ```sh
   .venv/bin/python scripts/build_st1704_at003_recovery_operator.py check
   .venv/bin/python scripts/build_st1704_at003_recovery_operator.py package
   ```

2. Review the package SHA-256 and install/activate only version `1.0.0` from the
   owner-private output directory. Keep `RAOS_AT003_RECOVERY_WRITES_ENABLED` absent
   or strict boolean `false` during installation and read-only review.
3. Confirm post 26 is the exact immutable Review Draft, post 19 is the exact Draft
   target with slug `carry-on-suitcase-comparison`, and post 19 has exactly the one
   existing category named `暮らしの道具`.
4. For a work window of at most 15 minutes, set the host constant to strict boolean
   `true`, open **Tools → AT-003 Draft recovery**, review every fixed binding and
   pre-state/operation hash, then enter the reason, final 12 operation-hash
   characters, and current WordPress password.
5. Submit once. On success, immediately disable the host constant, purge the cache,
   and run the exact carry-on public verification plus the browser matrix.
6. If the page refuses, the result is ambiguous, or readback/rollback fails, disable
   the host constant and stop. Do not delete the durable lock, retry automatically,
   publish another post, or advance to later articles.
