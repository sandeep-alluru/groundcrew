# GitHub Action

Use openveritas directly in your GitHub Actions workflow:

```yaml
- name: openveritas
  uses: sandeep-alluru/openveritas@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install openveritas
  run: pip install openveritas

- name: Run openveritas
  run: openveritas --help
```
