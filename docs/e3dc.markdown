---
title: E3/DC
description: Instructions on how to integrate an E3/DC home power station with Home Assistant over Modbus TCP.
ha_categories:
  - energy.solar_batteries
ha_release: "2026.12"
ha_iot_class: Local Polling
ha_codeowners:
  - '@AlCalzone'
ha_domain: e3dc
ha_platforms:
  - binary_sensor
  - diagnostics
  - number
  - sensor
  - switch
ha_config_flow: true
ha_integration_type: device
ha_quality_scale: bronze
ha_zeroconf: true
---

The **E3/DC** {% term integration %} connects Home Assistant to an E3/DC home power station from HagerEnergy over Modbus TCP. It reads the power flows between solar, battery, house, grid and wallboxes, and lets you control wallboxes and the battery.

## Use cases

- Seeing where your power goes. Solar production, battery charging and discharging, house consumption and grid import and export are all live sensors.
- Charging the car from the sun. Switch an E3/DC wallbox between solar-only and hybrid charging, or pause charging, from an automation.
- Charging the battery when power is cheap. With a dynamic tariff, an automation can charge the battery from the grid at night and stop when prices rise.
- Noticing when backup power is not ready. The **Emergency power ready** binary sensor shows whether the power station can switch to emergency power. How long it can then supply the house depends on the battery's charge, which the **Battery** sensor shows.

## Supported devices

The integration supports E3/DC home power stations whose Modbus interface uses the E3/DC protocol ("Simple Mode"), such as the S10 E, S10 E PRO, S10 X and S20 X PRO, and the systems running the Q10 and P10 firmware lines.

Newer firmware releases add registers: 32-bit power meter values, inverter data, remote control of the feed-in limit and the battery (from release 2025_06 and 2025_40), and the battery's limits and stored energy (from release 2026_04). The integration checks which of these your firmware serves during setup and adds only the matching entities.

## Unsupported devices

The SunSpec protocol mode of the Modbus interface is not supported. E3/DC systems reached only over the RSCP protocol are not supported either.

## Prerequisites

1. On the power station, go to **Main menu** > **Smart Functions** > **Smart Home** > **Modbus**.
2. Turn **Modbus** on, and set **Protocol** to **E3DC**.
3. Note the port. The default is `502`.

The power station answers Modbus requests only from devices in its own subnet.

{% include integrations/config_flow.md %}

{% configuration_basic %}
Host:
  description: "The hostname or IP address of the power station."
Port:
  description: "The Modbus TCP port set in the power station's Smart Home menu. The default is `502`."
{% endconfiguration_basic %}

A discovered power station is set up on the default port `502`. If you set a different port, add the integration manually.

{% note %}
Home Assistant can share a Modbus connection between integrations. Another integration that already talks to the same power station shares the connection instead of opening a second one.
{% endnote %}

## Reconfiguration

If the power station gets a new IP address, you can update it without removing the integration:

1. Go to {% my integrations title="**Settings** > **Devices & services**" %} and find the **E3/DC** integration.
2. Select the three-dot menu {% icon "mdi:dots-vertical" %} and choose **Reconfigure**.
3. Update the **Host** and **Port**, then select **Submit**.

The integration reads the serial number again and accepts the new settings only if they lead to the same power station.

## Supported functionality

### Sensors

The power station device has these sensors:

- **PV power**, **Battery power**, **House power** and **Grid power**, in watts. Battery power is positive while discharging and negative while charging. Grid power is positive while importing and negative while feeding in.
- **Wallbox power** and **Wallbox solar power**, in watts, if a wallbox is configured.
- **Additional feeder power**, in watts, if a power meter measures an additional feeder, such as a second PV inverter.
- **Battery**: the battery's state of charge.
- **Self-sufficiency** and **Self-consumption**, in percent.
- **Emergency power**, if the power station supports emergency power. It shows whether emergency power is active, inactive or not available. On the S10 E and S10 E PRO, **Motor switch off** means the emergency power motor switch is not in its on position.
- **Stored energy**, **Battery capacity**, **Maximum charge power** and **Maximum discharge power**, on firmware 2026_04 and later, if the power station reports its battery capacity.
- **Inverter mode**, the failsafe timeouts and the **SG Ready status**, as diagnostic sensors.

The integration checks for a wallbox and an additional feeder when it starts. After you add either one, reload the integration to get its power sensors.

Each configured power meter gets its own device with its type, its total power, and the power per phase, which is disabled by default. The power station's own inverter and each additional solar inverter also get a device with their power, voltage, current and frequency per phase, and the power, voltage and current of each DC tracker. Most inverter sensors are disabled by default.

### Binary sensors

- **Charging locked** and **Discharging locked**: the energy management system has blocked the battery.
- **Emergency power ready**: emergency power is available once the battery is charged.
- **Charging limited by forecast**: the weather forecast holds back charging capacity for the expected sunshine. This shows whether that is happening right now, not whether the forecast setting is on.
- **Feed-in limited**: output is throttled because the maximum feed-in was reached.
- **Charging lockout period** and **Discharging lockout period**: a lockout time from **Smart Charge** is active. Disabled by default.
- **Power output ready**: the inverter, DC-DC converter and battery are ready to deliver power.

Each wallbox gets its own device with **Charging**, **Type 2 plug**, **Type 2 plug locked** and **Type F plug** binary sensors.

### Numbers and switches for remote control

On firmware that supports remote control, the power station device has three setpoints. Each is a number and a switch:

- **Battery power setpoint** and **Battery power control**: charge (positive) or discharge (negative) the battery at a fixed power. PV power charges first, and the grid makes up the rest.
- **Feed-in limit setpoint** and **Feed-in limit control**: cap the power fed into the grid.
- **Active power limit setpoint** and **Active power limit control**: cap the inverter's output, as a percentage of its rated power. The cap ignores the house's consumption.

Setting a number writes the value to the power station and turns its switch on. The power station drops a setpoint 30 seconds after the last write, so while the switch is on, the integration writes the value again every 10 seconds. Turning the switch off hands control back: remote battery control ends at once, the integration writes 100 % as the active power limit, and the feed-in limit lapses within 30 seconds. Writing 100 % is itself a setpoint, so once the active power failsafe timeout runs out, the active power failsafe value applies. Check on your power station that this is what you want. Turning the switch on again holds the last value set, which is kept across restarts.

The numbers and switches stay usable while a poll fails, because holding a setpoint doesn't depend on the last poll.

A switch shows unknown while writing to the power station fails, because the power station may have dropped the setpoint. If a setpoint spans two registers and can only be half-written, setting it fails and the error says what the integration tried to put back.

### Wallbox switches

Each wallbox has these switches:

- **Charging**: turn off to stop charging.
- **Solar charging**: charge from solar power only. Turn off for hybrid charging, which also draws from the grid and the battery.
- **Single-phase charging**: charge on one phase instead of three.

Wallboxes, power meters and additional inverters appear when the power station reports them, including ones you add later. When the integration loads, it removes the devices of power meters that are no longer configured. A wallbox that is switched off, or an inverter that doesn't answer, looks the same as one that is gone, so you delete those devices yourself.

## Examples

### Charge the battery from the grid while power is cheap

This automation charges at 3 kW while a price sensor is below 15 cents, and hands the battery back when the price rises.

{% raw %}

```yaml
alias: "Charge the battery while power is cheap"
triggers:
  - trigger: numeric_state
    entity_id: sensor.electricity_price
    below: 0.15
    id: cheap
  - trigger: numeric_state
    entity_id: sensor.electricity_price
    above: 0.15
    id: expensive
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: cheap
        sequence:
          - action: number.set_value
            target:
              entity_id: number.s10_x_battery_power_setpoint
            data:
              value: 3000
      - conditions:
          - condition: trigger
            id: expensive
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.s10_x_battery_power_control
```

{% endraw %}

### Charge the car from solar only during the day

{% raw %}

```yaml
alias: "Solar charging during the day"
triggers:
  - trigger: sun
    event: sunrise
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.wallbox_0_solar_charging
```

{% endraw %}

## Data updates

The integration polls the power station every 5 seconds for its measurements, and every 60 seconds for its remote control settings. The power station accepts at most 10 requests per second, so the integration spaces its requests by 100 ms.

If one block of registers fails to read, only the entities from that block become unavailable.

## Known limitations

- The power station has no energy counters over Modbus. The Energy dashboard needs energy sensors, so you build them from the power sensors with helpers.
- The manual names the wallbox control bits, but which ones work depends on the wallbox model.
- A setpoint is held while Home Assistant runs. When Home Assistant stops, or when you reload or disable the integration, it hands every setpoint back, giving up after about 5 seconds on an unresponsive power station. If that fails, the switch shows off anyway. The battery power and the feed-in limit lapse within 30 seconds. The active power limit lasts for the active power failsafe timeout, after which the active power failsafe value applies. With a failsafe timeout of 0, it lasts until it is written again. After a restart, turn the setpoint's switch on again.

### Energy dashboard

**PV power** and **House power** are never negative. Create an [Integral](/integrations/integration/) helper from each of them. Set the metric prefix to **k** and the time unit to **Hours**, so the helper counts kWh.

**Grid power** and **Battery power** change sign with the direction of the flow. The Energy dashboard needs a separate counter for each direction, so split each sensor in two first:

1. Create a [Template](/integrations/template/) sensor helper for each direction. Set the unit to **W**, the device class to **Power** and the state class to **Measurement**. Replace the entity IDs with those of your power station.
   - Grid import: {% raw %}`{{ max(states('sensor.e3_dc_s10_x_grid_power') | float(0), 0) }}`{% endraw %}
   - Grid export: {% raw %}`{{ max(-(states('sensor.e3_dc_s10_x_grid_power') | float(0)), 0) }}`{% endraw %}
   - Battery charging: {% raw %}`{{ max(-(states('sensor.e3_dc_s10_x_battery_power') | float(0)), 0) }}`{% endraw %}
   - Battery discharging: {% raw %}`{{ max(states('sensor.e3_dc_s10_x_battery_power') | float(0), 0) }}`{% endraw %}
2. Create an Integral helper from each template sensor, with the metric prefix **k** and the time unit **Hours**.
3. In the Energy dashboard settings, add the grid import and export energy under **Electricity grid**, the PV energy under **Solar panels**, and the battery charging and discharging energy under **Home battery storage**.

## Troubleshooting

{% details "Setup reports that the device is not an E3/DC power station" %}

### Symptom: "The device answered, but it is not an E3/DC power station in E3/DC protocol mode"

When you add the integration, the form shows this error. An integration that was already set up stops with "The device is not an E3/DC power station in E3/DC protocol mode."

#### Description

The integration checks register 40001 for the E3/DC identifier. The power station reports it only while its Modbus interface uses the E3/DC protocol.

#### Resolution

1. On the power station, go to **Main menu** > **Smart Functions** > **Smart Home** > **Modbus**.
2. Set **Protocol** to **E3DC**, not **SUN_SPEC**.
3. Add the integration again, or reload it.

{% enddetails %}

{% details "Setup fails to connect" %}

### Symptom: "Failed to connect"

When you add the integration, the form shows this error. An integration that was already set up keeps retrying, and its sensors are unavailable.

#### Description

Home Assistant got no answer from the power station at the host and port you entered.

#### Resolution

1. Check that Modbus is turned on in the power station's **Smart Home** menu, and that the port matches.
2. Check that Home Assistant is in the same subnet as the power station. The power station answers Modbus requests only from devices in its own subnet.
3. Check that the host is the power station's current IP address. To keep it from changing, give the power station a fixed IP address in your router.

{% enddetails %}

{% details "Setup reports a different serial number" %}

### Symptom: "The device at this address has serial number …, not …"

An integration that worked before stops with this error.

#### Description

Home Assistant recognizes your power station by the serial number it read when you added the integration. A different power station now answers at the host and port of this entry. For example, your router gave the IP address to another E3/DC power station.

#### Resolution

1. If the power station of this entry moved to a new IP address, reconfigure the entry with that address. A fixed IP address in your router keeps it from moving again.
2. To use the power station that answers now, add it as a new entry.

{% enddetails %}

{% details "Remote control numbers and switches are missing" %}

### Symptom: The remote control numbers and switches are missing

The power station device has no numbers or switches for the battery power, the feed-in limit or the active power limit.

#### Description

The firmware does not serve the remote control registers.

#### Resolution

Update the power station's firmware, then reload the integration.

{% enddetails %}

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service.md %}

After removing the integration, turn Modbus off in the power station's **Smart Home** menu if nothing else uses it.
