# Catalog submission

`hermes-eye-memory.yaml` is ready to copy into `NousResearch/hermes-agent/plugin-catalog/`.

Before opening the PR:

1. Commit and push this repository.
2. Replace `sha` with the full 40-character commit SHA that reviewers should pin.
3. Confirm `plugin.yaml` and this entry have the same `requires_hermes` floor.
4. Run the local checks if you have Hermes installed:

```bash
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

5. Open the PR from the repository owner account. The catalog only accepts owner or major-contributor submissions.

The entry declares all 16 tools so the catalog's declared-capabilities check can compare them with `register()`.
