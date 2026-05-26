# Repository Guidelines

## Project Structure & Module Organization

This repository provides Linux deployment helpers for two proxy runtimes. Root-level `Script/` manages Mihomo downloads, subscriptions, systemd installation, and configuration enhancements. `sing_box/Script/` contains the equivalent sing-box flow; `sing_box/Script/Enhance/` holds Python conversion logic and its tests. `ruleset/` contains Mihomo rule data. Generated runtime assets such as `mihomo`, `sing_box/sing-box`, `ui/`, `sing_box/ui/`, `config.yaml`, and `sing_box/config.json` are local artifacts and may contain credentials.

## Build, Test, and Development Commands

There is no build system; use the repository scripts directly:

```bash
./Script/update_core_assets.sh                     # fetch Mihomo and assets
./sing_box/Script/update_sing_box_core.sh           # fetch sing-box and UI
./sing_box/Script/Enhance/clash_nodes_to_singbox.py # generate sing_box/config.json
./sing_box/sing-box check -c ./sing_box/config.json # validate sing-box config
python3 -m unittest sing_box.Script.Enhance.test_clash_nodes_to_singbox
sudo ./sing_box/Script/setup_sing_box_service.sh --no-start
```

Use `--no-start` while changing TUN or DNS behavior so configuration can be inspected before network routing changes.

## Coding Style & Naming Conventions

Shell scripts use Bash with `set -euo pipefail`, uppercase configuration constants, and quoted variable expansions. Python uses four-space indentation, type hints, `snake_case` functions, and `UPPER_CASE` constants. Keep enhancement scripts narrowly focused and preserve existing command-line interfaces. No project-wide formatter or linter is configured; match surrounding style.

## Testing Guidelines

Python tests use `unittest` and are named `test_*.py` next to the converter code. Add regression tests for DNS, routing, outbound-group, and conversion changes before modifying implementation. Validate generated sing-box configuration with `sing-box check`; do not treat starting a TUN service as a test step.

## Commit & Pull Request Guidelines

Recent history uses short subjects such as `Update`, `Enhance`, and `Debug`. Prefer a more descriptive imperative subject, for example `Fix sing-box TUN DNS routing`. Pull requests should state which runtime is affected, list validation commands, describe service or routing impact, and call out any generated configuration intentionally excluded from version control.

## Security & Configuration Tips

Never commit subscription URLs, tokens, node credentials, UI secrets, or runtime configuration containing them. Redact logs and screenshots before sharing. Treat systemd installation and TUN startup as privileged, network-affecting operations.
