# Handoff: E3/DC follow-up pull requests

Written on 2026-11-06. The goal is the full integration from this repository in Home Assistant core, one feature per pull request. Nothing goes out as a HACS integration.

## Where things stand

- **Core:** home-assistant/core#189806 is merged as `a132cfb`. It has the config flow with zeroconf discovery and the sensor platform, at Bronze.
- **Brands:** home-assistant/brands#11393 is merged.
- **Docs:** home-assistant/home-assistant.io#50091 is open against `next`, from `AlCalzone:e3dc-docs` at `9a47d26`. It still needs to be merged.
- **Staging:** `main` here is at `436125b`. It has every change from the merged core pull request ported back. 72 tests pass.
- **Real hardware:** the merged integration works against the real power station on core `dev`.

## Follow-up branches

All eight are pushed. Merged: diagnostics (home-assistant/core#190876) and the `e3dc-ess-modbus` 0.2.0 bump (home-assistant/core#190888). Open: binary sensors as home-assistant/core#190858 and home-assistant/home-assistant.io#50272, reconfigure as home-assistant/core#190872 and home-assistant/home-assistant.io#50274, the diagnostics docs as home-assistant/home-assistant.io#50275, station sensors as home-assistant/core#190878 and home-assistant/home-assistant.io#50276.

| Feature | Core branch on `AlCalzone/homeassistant-core` | Docs branch on `AlCalzone/home-assistant.io` | PR bodies in `handoff/pr-bodies/` |
|---|---|---|---|
| Binary sensors | `e3dc-binary-sensors` at `c5eb6f5` | `e3dc-binary-sensors-docs` at `8ecaf48` | `binary-sensors-core.md`, `binary-sensors-docs.md` |
| Reconfigure flow | `e3dc-reconfigure` at `21eb797` | `e3dc-reconfigure-docs` at `8a0a3ea` | `reconfigure-core.md`, `reconfigure-docs.md` |
| Diagnostics | `e3dc-diagnostics` at `f5c70ee` | `e3dc-diagnostics-docs` at `3a98b5b` | `diagnostics-core.md`, `diagnostics-docs.md` |
| Station sensors | `e3dc-station-sensors` at `644636d` | `e3dc-station-sensors-docs` at `58fa3d0` | `station-sensors-core.md`, `station-sensors-docs.md` |

The core branches start from core `dev` after the merge of #189806. The docs branches start from `e3dc-docs`, because #50091 isn't merged yet.

What each one adds:

- **Binary sensors:** seven EMS status flags from register 40085. The charge and discharge lock time flags are disabled by default. It adds `icons.json` with four icons and sets `entity-disabled-by-default: done`. The test fixture `platforms` now defaults to the integration's real `PLATFORMS`. The per-platform tests narrow it.
- **Reconfigure flow:** `async_step_reconfigure` changes the host and port. It aborts with `unique_id_mismatch` when a different power station answers. The serial number mismatch error now points the user to reconfiguration. The docs get a Reconfiguration section.
- **Diagnostics:** the config entry, the coordinator data and a raw register read of the identity, polled and hardware blocks. The serial number registers are dropped and the serial number is redacted. The docs only add `diagnostics` to `ha_platforms`.
- **Station sensors:** polls `battery_limits`, `wide_power_meters`, `inverter_mode_control` and `grid_control` every 5 seconds. Each sensor description names its component, and only sensors for blocks the power station serves are created. It sets `entity-category: done` and `entity-disabled-by-default: done`, and adds the `inverter_mode` icon.

## Getting the branches on the laptop

```bash
git fetch origin e3dc-binary-sensors e3dc-reconfigure e3dc-diagnostics e3dc-station-sensors
```

```bash
git fetch origin e3dc-binary-sensors-docs e3dc-reconfigure-docs e3dc-diagnostics-docs e3dc-station-sensors-docs
```

Run the first in the core checkout and the second in the home-assistant.io checkout. Both assume `origin` is the fork. Run `script/setup` in a fresh core worktree before committing.

## Opening the pull requests

1. Read each PR body draft. They follow the full templates. The cross-link lines are empty because the other pull request doesn't exist yet.
2. Open the core pull request from the fork branch against `dev`.
3. Open the docs pull request against `next`.
4. Fill in the cross-links in both descriptions.

If a docs pull request opens before #50091 merges, its diff also shows #50091's changes. Rebasing a docs branch onto `next` after #50091 merges is fine as long as its pull request isn't open yet. Once a pull request is open, don't amend, squash or rebase its pushed commits.

## Conflicts between the four

The four branches touch the same few files. Whichever merges second needs these fixes:

- **`icons.json`:** binary sensors and station sensors both create it. Merge the two `entity` sections by hand.
- **`ha_platforms` in the docs:** binary sensors adds `binary_sensor`, diagnostics adds `diagnostics`. Keep both, in alphabetical order.
- **Diagnostics snapshot:** done on `e3dc-station-sensors` in `644636d`, after merging `dev` with the diagnostics PR.
- **`quality_scale.yaml`:** binary sensors and station sensors make the same `entity-disabled-by-default` change. It merges cleanly.

## After these four

These have to go one after another, because each builds on the previous one:

1. Power meter and inverter devices with their sensors.
2. Wallbox devices with sensors and switches, added when the power station reports them.
3. Stale device removal.
4. Remote control: the settings coordinator, setpoint holds, numbers and switches.
5. Raise the declared quality tier once its rules are all met.

Each one also updates `quality_scale.yaml`, the docs page and the tests. `TODO.md` keeps the longer list, including the open items outside the pull requests.

## Testing this repository against core

`script/install-into-core.sh ../core` copies the integration into a core checkout. To run the tests by hand:

1. Copy `homeassistant/components/e3dc` and `tests/components/e3dc` into the core checkout.
2. Run `uv run --no-sync python -m script.translations develop --integration e3dc`. Plain `python3` lacks `orjson`.
3. Run `uv run --no-sync pytest tests/components/e3dc` and `uv run --no-sync prek run --all-files`.
4. Copy any snapshot or formatting changes back here.
5. Reset the core checkout with `git checkout -- homeassistant/components/e3dc tests/components/e3dc` and `git clean -fd` on the same paths.

## Rules for this work

- A human reviews every change before it's submitted. Don't open pull requests or post comments without that review.
- Never remove anything from the PR templates, including unchecked boxes.
- No attribution lines in commits or PR descriptions.
- No forced line breaks in GitHub prose.
- Tests check behavior that catches regressions. They don't pin down a scope that the next feature is meant to extend.

## Other branches

`e3dc-integration` on the core fork is the October working branch from before this repository existed. It's pushed as a backup. This repository supersedes it.
