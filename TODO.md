# Getting `e3dc` into Home Assistant core

This repository holds the full integration. Core takes it in small pull requests: the first one has the config flow and one platform at the Bronze tier, and every later one adds one feature. The steps below follow [Creating your first integration](https://contributors.home-assistant.io/core/integrations/create/) and [Submitting a pull request](https://contributors.home-assistant.io/core/development/submitting/#new-integrations).

## 1. Before anything is submitted

- [x] Fix the tests against core `dev`. Core now rejects a boolean from `async_setup_entry` and `async_unload_entry` (home-assistant/core#187778), and its snapshots now show `device_id` and `config_subentry_id`.
- [x] Add `timeout-minutes: 20` to the CI job. The run for `8988414` hung until GitHub cancelled it after 6 hours.
- [x] Commit both.
- [ ] Fix CI on `main`. Since 2026-11-06 it fails at installing core and the test dependencies.
- [x] Raise `homeassistant` in `hacs-e3dc/hacs.json` to `2026.11.0b0`. That is the first release with `async_unload_platforms_or_raise` (home-assistant/core#185989) and with `None` accepted from `async_setup_entry` (home-assistant/core#187778). 2026.10 treats `None` as a failed setup.
- [x] Not needed any more, because home-assistant/core#189806 is merged: ask in the [#core channel](https://discord.com/channels/330944238910963714/1475552721515053268) whether `e3dc` belongs in core. The guide wants a custom integration with a user base first. `e3dc` goes straight to core, with no custom integration release.
- [x] Test against a real power station.
- [x] Remove the "not tested on real hardware" notes from the library README and from this repository's README.

## 2. Publish `e3dc-ess-modbus` 0.1.0

The [dependency-transparency](https://contributors.home-assistant.io/core/quality-scale/dependency-transparency/) rule wants an OSI license, a PyPI release built by public CI, and a git tag for every PyPI version. The repository has the Apache 2.0 license and `publish.yml` already. The `pypi` environment exists, with required reviewers and the `*.*.*` tag rule.

- [x] On PyPI, add a pending trusted publisher: project `e3dc-ess-modbus`, owner `AlCalzone`, repository `e3dc-ess-modbus`, workflow `publish.yml`, environment `pypi`.
- [x] Check that CI is green on `main`.
- [x] Draft a GitHub release with the tag `0.1.0` on `main`, and publish it.
- [x] Approve the `publish` job in the Actions tab.
- [x] Check that https://pypi.org/project/e3dc-ess-modbus/0.1.0/ exists.
- [x] Switch the CI here from the git install to `e3dc-ess-modbus==0.1.0`.
- [x] Set `dependency-transparency: done` in `quality_scale.yaml`.

## 3. Brand images

Brands live in [home-assistant/brands](https://github.com/home-assistant/brands), in `core_integrations/<domain>/`. The repository already has `custom_integrations/e3dc`, from home-assistant/brands#9209 for [e3dc-homeassistant](https://github.com/JohannLegler/e3dc-homeassistant). The brands README says a core domain takes precedence over a custom one, so this doesn't block the core domain.

- [x] Keep the domain `e3dc`. Sofar was submitted as `sofar_modbus`, and @joostlek asked in review "why sofar_modbus, and why not sofar?" (home-assistant/core#179329). It was renamed to `sofar`.
- [ ] Let @JohannLegler know that a core integration takes the `e3dc` domain. Their custom integration overrides the core one for anyone who has it installed. After removing it, their entries fail core's serial number check, because their unique ID is the host, so users have to set them up again.
- [x] Open the brands pull request: home-assistant/brands#11393 moves the 8 existing images from `custom_integrations/e3dc` to `core_integrations/e3dc`.
- [x] Set `brands: done` in `quality_scale.yaml`, with the brands pull request linked from the core one.
- [x] Get home-assistant/brands#11393 merged.

## 4. First core pull request: config flow and sensors

Scope: Bronze tier, one platform, nothing extra. Core reviewers close large first pull requests.

Keep:

- [x] `manifest.json`, with `"quality_scale": "bronze"`.
- [x] `config_flow.py` with the user step only.
- [x] `__init__.py` with setup, the serial number check and unload. Only the sensor platform.
- [x] `coordinator.py` with the readings coordinator only.
- [x] `entity.py` with the base entity on the power station device only.
- [x] `sensor.py` with the `power` block only: PV, battery, house, grid, additional feeder and wallbox power, battery state of charge, autarky, self-consumption, and the emergency power status.
- [x] `strings.json` trimmed to the kept entities, errors and exceptions.
- [x] `quality_scale.yaml` with every Bronze rule `done` or `exempt`. Every higher rule goes back to `todo`, except the ones that are honestly `exempt`.
- [x] Tests: `test_config_flow.py`, `test_init.py`, `test_sensor.py` and the sensor snapshot. Full coverage of `config_flow.py`, the rest above 95 %.

Leave out, for later pull requests:

- `reconfigure` step, `diagnostics.py`, `icons.json` (unless a kept entity needs it).
- The settings coordinator, `holds.py`, `number.py`, `switch.py`, `binary_sensor.py`.
- Sensors from `battery_limits`, `grid_control`, `wide_power_meters` and `inverter_mode_control`.
- Power meter, inverter and wallbox devices, adding them on the fly, and removing stale ones.

Steps:

- [x] Branch from the latest core `dev`.
- [x] Copy the trimmed integration and tests into core.
- [x] Add the domain to `.strict-typing`.
- [x] Run `python3 -m script.hassfest` and `python3 -m script.gen_requirements_all`. They update `CODEOWNERS`, `homeassistant/generated/config_flows.py`, `homeassistant/generated/integrations.json`, `mypy.ini` and `requirements_all.txt`.
- [x] Run `python3 -m script.translations develop --integration e3dc`, then `uv run --no-sync pytest tests/components/e3dc`.
- [x] Run `uv run --no-sync prek run --all-files`.
- [x] Set the integration up in a running Home Assistant against the real power station.
- [x] Search the diff for `TODO`.
- [x] Open the pull request as a draft with the full template: home-assistant/core#189806, from `AlCalzone:add-e3dc-integration`. It links the library repository, the `publish.yml` workflow and the `0.1.0` tag.
- [x] Link the brands pull request in its description, and set `brands: done`.
- [x] Link the docs pull request in its description.
- [x] Mark the core, docs and brands pull requests ready for review.
- [x] Port the review fixes from home-assistant/core#189806 here: close the station after a failed probe in the config flow.
- [x] In e3dc-ess-modbus, make `async_detect()` close the station when setup fails.
- [x] Port the later review changes here: zeroconf discovery, sensors only for installed hardware, battery power positive while discharging, and aborting discovery when the probe fails.
- [x] Get home-assistant/core#189806 merged.
- [x] Release the `async_detect()` fix. It went out in e3dc-ess-modbus 0.2.0 instead of 0.1.1.
- [x] Sign the CLA if the bot asks.

## 5. Documentation pull request

- [x] Trim `docs/e3dc.markdown` to the first pull request: `ha_platforms: [sensor]`, no reconfiguration section, no binary sensor, number, switch or wallbox sections, and no examples that need them.
- [x] Target 2026.12 with `ha_release`. The 2026.12 beta starts at the end of November, so the core pull request has to be merged before then. Otherwise, bump the release.
- [x] Open it against the `next` branch of home-assistant.io and link it from the core pull request: home-assistant/home-assistant.io#50091, as a draft.
- [x] Get home-assistant/home-assistant.io#50091 merged.

## 6. Follow-up pull requests

One feature each. Each one updates `quality_scale.yaml`, the docs page and the tests. Since the station sensors, these are written in the core fork first. The changes here lag behind core and need porting back.

Merged in core, docs still open against `next`:

- [x] Binary sensors for the EMS status bits: home-assistant/core#190858. Docs: home-assistant/home-assistant.io#50272.
- [x] Reconfigure flow: home-assistant/core#190872. Docs: home-assistant/home-assistant.io#50274.
- [x] Diagnostics: home-assistant/core#190876. Docs: home-assistant/home-assistant.io#50275.
- [x] Bump e3dc-ess-modbus to 0.2.0: home-assistant/core#190888.
- [x] Remaining station sensors: battery limits, failsafe timeouts, inverter mode, SG Ready. home-assistant/core#190878. Docs: home-assistant/home-assistant.io#50276.
- [x] Raise the declared tier to Silver: home-assistant/core#190972.
- [ ] Get the four docs pull requests merged.

Still to do:

- [ ] Power meter and inverter devices with their sensors: home-assistant/core#191296 and home-assistant/home-assistant.io#50340, both drafts. Tested on the real power station. Each device is named after its slot, e.g. **Inverter 1** and **Power meter 2**. What's left:
  - [ ] Get home-assistant/core#191296 and home-assistant/home-assistant.io#50340 merged.
  - [ ] Move the part discovery from `sensor.py` into the coordinator. It should keep the present slots per kind once per poll. `E3dcPartSensor.available` then becomes a set lookup, and stale device removal gets a place to live. Plugwise does it this way.
  - [ ] Check the grid meter in one place. `_grid_meter` and the `exists_fn` of the grid phase sensors ignore `is_installed`, but `_installed_meters` checks it.
  - [ ] Decide whether inverter slots that answer without an inverter should be polled less often. All 8 slots cost 3 Modbus requests per poll, against 1 for slot 0 alone. That probably needs a knob in e3dc-ess-modbus.
- [ ] Remote control: setpoint holds, numbers and switches. Branches `e3dc-remote-control` on the core fork and `e3dc-remote-control-docs` on the docs fork, based on `dev` and `next`. No pull requests yet. Parked until there is time to test the writes on the real power station.
- [ ] Wallbox devices with sensors and switches, added when the power station reports them. Comes after remote control, because both add to `switch.py`.
- [ ] Stale device removal, on top of the power meter and inverter devices.
- [ ] Dynamic devices. `dynamic-devices` is `todo` again, because two cases still need a reload:
  - An inverter slot that refuses or times out during setup. `E3dcPowerStation` only looks for inverters during setup. Add a way to look at the missing slots again to e3dc-ess-modbus, release it, and bump it in core in its own pull request. Then have the coordinator call it now and then.
  - A wallbox configured after setup. Handle it in the wallbox pull request.
- [ ] Raise the declared tier to Gold once its rules are all met.
