# E3/DC integration for Home Assistant core

The `e3dc` integration for [Home Assistant core](https://github.com/home-assistant/core), staged here until it is submitted. It connects an E3/DC home power station over Modbus TCP, through the device library [e3dc-ess-modbus](https://github.com/AlCalzone/e3dc-ess-modbus).

The layout mirrors core's, so the files copy straight across:

```text
homeassistant/components/e3dc/   the integration
tests/components/e3dc/           its tests and snapshots
docs/e3dc.markdown               the page for home-assistant.io
```

## What it does

- A config flow that asks for the host and port, and checks register 40001 for the E3/DC identifier. The unit ID is fixed at 1.
- Two coordinators: measurements every 5 seconds, remote control settings every 60.
- Sensors for the power flows, battery, DC strings, power meters and inverters, and binary sensors for the EMS status bits.
- A device per wallbox, with charging, solar mode and phase switches. Wallboxes the power station reports later are added on the fly.
- A number and a switch per remote setpoint (battery power, feed-in limit, active power limit). Setting the number writes it, and the integration rewrites it every 10 seconds while the switch is on.
- Diagnostics with the raw register dump. The serial number registers are left out.

It takes its Modbus unit from core's `modbus` integration with `async_get_unit`, so it shares the connection with any other integration that talks to the same power station.

## Trying it in a core checkout

```bash
script/install-into-core.sh ../core
```

The script copies the integration and its tests into the checkout and adds it to `.strict-typing`. When the checkout has a `.venv`, it also regenerates the translations, `CODEOWNERS`, the generated config flow list, `mypy.ini` and `requirements_all.txt`.

Until `e3dc-ess-modbus` is on PyPI, install it from git into core's venv:

```bash
uv pip install --python ../core/.venv/bin/python "e3dc-ess-modbus @ git+https://github.com/AlCalzone/e3dc-ess-modbus@main"
```

Then run the tests from the core checkout:

```bash
.venv/bin/python -m pytest tests/components/e3dc
```

CI does the same against core's `dev` branch on every push and once a week.

## Before submitting

- Publish `e3dc-ess-modbus` 0.1.0 to PyPI. The manifest pins it.
- Add the E3/DC brand to [home-assistant/brands](https://github.com/home-assistant/brands). Until then hassfest fails the `brands` rule of the Bronze tier, which every new integration has to reach. The brands repository already has `custom_integrations/e3dc`, added for [e3dc-homeassistant](https://github.com/JohannLegler/e3dc-homeassistant) in home-assistant/brands#9209. That folder has to be resolved with its owner before core can use the domain.
- Open the documentation pull request on home-assistant.io with `docs/e3dc.markdown`.
- Test against a real power station. The register map comes from the manufacturer's manual, version 2.80, and has only been tested against the mock.
