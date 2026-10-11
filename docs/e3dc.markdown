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
  - number
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
- **Inverter mode**, the failsafe timeouts and the **SG Ready status**, as diagnostic sensors.

Each configured power meter gets its own device with its type, its total power, and the power per phase, which is disabled by default. The power station's own inverter and each additional solar inverter also get a device with their power, voltage, current and frequency per phase. Most inverter sensors are disabled by default.

### Binary sensors

- **Charging locked** and **Discharging locked**: the energy management system has blocked the battery.
- **Emergency power ready**: emergency power is available once the battery is charged.
- **Weather-based charging**: charging capacity is held back for the expected sunshine.
- **Feed-in limited**: output is throttled because the maximum feed-in was reached.
- **Charging lockout period** and **Discharging lockout period**: a lockout time from **Smart Charge** is active. Disabled by default.
- **Power output ready**: the inverter, DC-DC converter and battery are ready to deliver power.

Each wallbox gets its own device with **Charging**, **Type 2 plug**, **Type 2 plug locked** and **Type F plug** binary sensors.

### Numbers and switches for remote control

On firmware that supports remote control, the power station device has three setpoints. Each is a number and a switch:

- **Battery power setpoint** and **Battery power control**: charge (positive) or discharge (negative) the battery at a fixed power. PV power charges first, and the grid makes up the rest.
- **Feed-in limit** and **Feed-in limit control**: cap the power fed into the grid.
- **Active power limit** and **Active power limit control**: cap the inverter's output, as a percentage of its rated power. The cap ignores the house's consumption.

Setting a number writes the value to the power station and turns its switch on. The power station drops a setpoint 30 seconds after the last write, so while the switch is on, the integration writes the value again every 10 seconds. Turning the switch off hands control back: remote battery control ends at once, the active power limit goes back to 100 %, and the feed-in limit lapses within 30 seconds. Turning the switch on again holds the last value set.

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

- The power station has no energy counters over Modbus. To use it on the Energy dashboard, create [Integral](/integrations/integration/) helpers from the power sensors.
- The manual names the wallbox control bits, but which ones work depends on the wallbox model.
- A setpoint is held while Home Assistant runs. When Home Assistant stops, the integration hands every setpoint back. If that fails, the battery power and the feed-in limit lapse within 30 seconds. The active power limit lasts for the active power failsafe timeout, after which the active power failsafe value applies. With a failsafe timeout of 0, it lasts until it is written again. After a restart, set the setpoint again.

## Troubleshooting

### The device is not an E3/DC power station

Setup reports this when register 40001 does not hold the E3/DC identifier. Check that **Protocol** is set to **E3DC** in the power station's **Smart Home** > **Modbus** menu, not **SUN_SPEC**.

### Failed to connect

- Check that Modbus is turned on and the port matches.
- Check that Home Assistant is in the same subnet as the power station.

### The remote control numbers and switches are missing

The firmware does not serve the remote control registers. Update the power station's firmware.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service_steps.md %}

After removing the integration, turn Modbus off in the power station's **Smart Home** menu if nothing else uses it.
