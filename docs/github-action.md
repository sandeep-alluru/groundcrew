# GitHub Action

Use groundcrew directly in your GitHub Actions workflow:

```yaml
- name: groundcrew
  uses: sandeep-alluru/groundcrew@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install groundcrew
  run: pip install groundcrew

- name: Run groundcrew
  run: groundcrew --help
```
