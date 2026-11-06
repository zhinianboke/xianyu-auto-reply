# Agent Ops CLI

Local CLI for operating the running `xianyu-auto-reply` stack without clicking
through the web UI.

Read-only commands can inspect health, Docker containers, MySQL counts, and
scheduled tasks. Write commands call the backend API and require `--yes`, or
can be previewed with `--dry-run`.

## Examples

```bash
./agent-ops status
./agent-ops auth local-token --write-token-file .agent-ops-token
./agent-ops --token-file .agent-ops-token accounts list
./agent-ops --token-file .agent-ops-token tasks list
./agent-ops --token-file .agent-ops-token tasks trigger fetch_orders --dry-run
./agent-ops --token-file .agent-ops-token accounts set-reply-delay <account-id> 2 --yes
./agent-ops --token-file .agent-ops-token keywords add <account-id> --keyword "在吗" --reply "在的" --dry-run
```

Output is redacted by default for fields such as cookies, passwords, tokens,
API keys, and generic backend `value` fields. Pass `--show-sensitive` only when
you intentionally need raw values.

High-risk operations such as sending messages, delivery, cancellation, login
renewal, and product publishing are intentionally not exposed in this first CLI
surface.
