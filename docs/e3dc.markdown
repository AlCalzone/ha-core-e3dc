---
title: E3/DC
description: Instructions on how to integrate an E3/DC home power station with Home Assistant over Modbus TCP.
ha_category:
  - Energy
  - Modbus-controlled
ha_release: 2026.11
ha_iot_class: Local Polling
ha_codeowners:
  - '@AlCalzone'
ha_domain: e3dc
ha_platforms:
  - binary_sensor
  - diagnostics
  - sensor
  - switch
ha_config_flow: true
ha_integration_type: device
ha_quality_scale: bronze
---

The **E3/DC** {% term integration %} connects Home Assistant to an E3/DC home power station from HagerEnergy over Modbus TCP. It reads the power flows between solar, battery, house, grid and wallboxes, and lets you control wallboxes and the battery.

## Use cases

- Seeing where your power goes. Solar production, battery charging and discharging, house consumption and grid import and export are all live sensors.
- Charging the car from the sun. Switch an E3/DC wallbox between solar-only and hybrid charging, or pause charging, from an automation.
- Charging the battery when power is cheap. With a dynamic tariff, an automation can charge the battery from the grid at night and stop when prices rise.
- Noticing when backup power is not ready. The emergency power sensor shows whether the house would stay powered in a grid failure.

## Supported devices

The integration supports E3/DC home power stations whose Modbus interface uses the E3/DC protocol ("Simple Mode"), such as the S10 E, S10 E PRO, S10 X and S20 X PRO, and the systems running the Q10 and P10 firmware lines.

Newer firmware releases add registers: 32-bit power meter values, inverter data, remote control of the feed-in limit and the battery (from release 2025_06 and 2025_40), and the battery's limits and stored energy (from release 2026_04). The integration checks which of these your firmware serves during setup and adds only the matching entities and actions.

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

- **PV power**, **Battery power**, **House power**, **Grid power**, **Additional feeder power**, **Wallbox power** and **Wallbox solar power**, in watts. Battery power is positive while charging. Grid power is positive while importing and negative while feeding in.
- **Battery**: the battery's state of charge.
- **Self-sufficiency** and **Self-consumption**, in percent.
- **Emergency power**: whether emergency power is active, inactive, not available or not supported. On the S10 E and S10 E PRO, **Motor switch off** means the emergency power motor switch is not in its on position.
- **DC string 1 power** and **DC string 2 power**, plus their voltage and current, which are disabled by default.
- **Stored energy**, **Battery capacity**, **Maximum charge power** and **Maximum discharge power**, on firmware 2026_04 and later.
- **Inverter mode**, **Feed-in limit**, the failsafe timeouts and the **SG Ready status**, as diagnostic sensors.

Each configured power meter gets its own device with its type, its total power, and the power per phase, which is disabled by default. The power station's own inverter and each additional solar inverter also get a device with their power, voltage, current and frequency per phase. Most inverter sensors are disabled by default.

### Binary sensors

- **Charging locked** and **Discharging locked**: the energy management system has blocked the battery.
- **Emergency power ready**: emergency power is available once the battery is charged.
- **Weather-based charging**: charging capacity is held back for the expected sunshine.
- **Feed-in limited**: output is throttled because the maximum feed-in was reached.
- **Charging lockout period** and **Discharging lockout period**: a lockout time from **Smart Charge** is active. Disabled by default.
- **Power output ready**: the inverter, DC-DC converter and battery are ready to deliver power.

Each wallbox gets its own device with **Charging**, **Type 2 plug**, **Type 2 plug locked** and **Type F plug** binary sensors.

### Switches

Each wallbox has these switches:

- **Charging**: turn off to stop charging.
- **Solar charging**: charge from solar power only. Turn off for hybrid charging, which also draws from the grid and the battery.
- **Single-phase charging**: charge on one phase instead of three.

Wallboxes appear when the power station reports them, including ones you add later.

## Actions

All actions require an administrator and are available only on firmware that serves the registers they write.

### Action: Set battery power

The `e3dc.set_battery_power` action charges or discharges the battery at a fixed power. Positive values charge, negative values discharge. PV power charges the battery first, and the grid makes up the rest.

The power station returns to its own control 30 seconds after the last call, so call the action again at least every 30 seconds to hold the setpoint.

| Data attribute | Optional | Description |
| --- | --- | --- |
| `config_entry_id` | no | The power station to control. |
| `power` | no | The battery power in watts. |

### Action: Stop battery control

The `e3dc.stop_battery_control` action ends remote battery control at once, without waiting for the 30-second timeout.

| Data attribute | Optional | Description |
| --- | --- | --- |
| `config_entry_id` | no | The power station to control. |

### Action: Set feed-in limit

The `e3dc.set_feed_in_limit` action caps the power fed into the grid. Like the battery power, the limit expires 30 seconds after the last call.

| Data attribute | Optional | Description |
| --- | --- | --- |
| `config_entry_id` | no | The power station to control. |
| `power` | no | The most power to feed into the grid, in watts. |

### Action: Set active power limit

The `e3dc.set_active_power_limit` action caps the inverter's active power as a percentage of its rated power. The cap ignores the house's consumption. It expires after the active power failsafe timeout, 30 seconds by default.

| Data attribute | Optional | Description |
| --- | --- | --- |
| `config_entry_id` | no | The power station to control. |
| `limit` | no | The output ceiling, in percent of rated power. |

## Examples

### Charge the battery from the grid while power is cheap

This automation holds a 3 kW charge every 20 seconds while a price sensor is below 15 cents, and hands control back when it rises.

{% raw %}

```yaml
alias: "Charge the battery while power is cheap"
triggers:
  - trigger: time_pattern
    seconds: "/20"
conditions:
  - condition: numeric_state
    entity_id: sensor.electricity_price
    below: 0.15
  - condition: numeric_state
    entity_id: sensor.s10_x_battery
    below: 95
actions:
  - action: e3dc.set_battery_power
    data:
      config_entry_id: YOUR_CONFIG_ENTRY_ID
      power: 3000
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

- The power station has no energy counters over Modbus. To use it on the Energy dashboard, create [Integral](/integrations/integration/) helpers from the power sensors.
- The manual names the wallbox control bits, but which ones work depends on the wallbox model.
- Remote control setpoints expire after 30 seconds, so automations have to repeat them.

## Troubleshooting

### The device is not an E3/DC power station

Setup reports this when register 40001 does not hold the E3/DC identifier. Check that **Protocol** is set to **E3DC** in the power station's **Smart Home** > **Modbus** menu, not **SUN_SPEC**.

### Failed to connect

- Check that Modbus is turned on and the port matches.
- Check that Home Assistant is in the same subnet as the power station.

### An action says the power station does not support it

The firmware does not serve the registers the action writes. Update the power station's firmware.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service_steps.md %}

After removing the integration, turn Modbus off in the power station's **Smart Home** menu if nothing else uses it.
