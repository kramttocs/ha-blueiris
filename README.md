# <img src="custom_components/blueiris/brand/icon.png" alt="Blue Iris logo" width="42"> Blue Iris
![HomeAssistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-blue.svg)
![Maintenance](https://img.shields.io/badge/Maintained-Yes-brightgreen.svg)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.6%2B-blue)

Home Assistant integration for **Blue Iris Video Security Software**.

This is/was designed (original design by elad-bar), reviewed, and tested by me. AI assisted.

This integration allows Home Assistant to interact with your Blue Iris server, providing cameras, sensors, profile control, motion event tracking, snapshot support, and automation-friendly entities.

> [!WARNING]
> Do not install this over elad-bar's version. Remove that Blue Iris integration (both from the Integration page as well as from your HACS list)
> Both integrations use the same Home Assistant domain, so they cannot coexist.
>

> [!IMPORTANT]
> This integration also changes how the MQTT messages/topics are setup in Blue Iris to allow for multiple Blue Iris servers.
> Please see the linked Manual

📄 **Changelog**  
[CHANGELOG.md](https://github.com/kramttocs/ha-blueiris/blob/main/CHANGELOG.md)

📄 **Manual**  
[docs/bi-manual.md](https://github.com/kramttocs/ha-blueiris/blob/main/docs/bi-manual.md)

---

# Table of Contents

- [Credit](#credit)
- [Installation and Setup](#installation-and-setup)
  - [Requirements](#requirements)
  - [Installation via HACS](#installation-via-hacs)
- [Integration Configuration](#integration-configuration)
  - [Basic Setup](#basic-setup)
- [Integration Options](#integration-options)
- [AI Label Mapping](#ai-label-mapping)
- [Entities and Components](#entities-and-components)
  - [Binary Sensors](#binary-sensors)
  - [Last Motion Event Sensors](#last-motion-event-sensors)
  - [Update Sensors](#update-sensors)
  - [Camera Entity](#camera-entity)
  - [Profile and Schedule Selects](#profile-and-schedule-selects)
  - [Hold Profile Changes Switch](#hold-profile-changes-switch)
- [Services](#services)
  - [Latest Motion Event Snapshot](#latest-motion-event-snapshot)
  - [Trigger Camera](#trigger-camera)
  - [Move to Preset](#move-to-preset)
  - [Reload](#reload)
- [Blueprint](#blueprint)
  - [Blue Iris - Last Motion Event Notifications](#blue-iris---last-motion-event-notifications)
- [Example Automation](#example-automation)

---

# Credit

Really appreciate the support team at Blue Iris Software.

This integration builds upon the excellent work originally created by **elad-bar**.

---

# Installation and Setup

## Requirements

- A **Blue Iris server** accessible from Home Assistant
- A **user account** configured in Blue Iris
- A **Server Name** configured in Blue Iris settings
- To control **Profiles**, the user must have **Admin permissions**
- **MQTT integration (optional)** for real-time event updates

## Installation via HACS Custom Repository

> [!NOTE]
> This integration is currently installed through HACS as a **custom repository**. It is not yet available in the default HACS repository list.

1. Open **HACS**
2. Open the **three-dot menu** in the top-right corner
3. Select **Custom repositories**
4. Add this repository URL:

   ```text
   https://github.com/kramttocs/ha-blueiris
   ```

5. Set the category to **Integration**
6. Click **Add**
7. Search for **Blue Iris** in HACS
8. Install the integration
9. Restart Home Assistant if prompted

---

# Integration Configuration

## Basic Setup

`Configuration → Integrations → Add Integration → Blue Iris`

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| Host | Textbox | Yes | None | Hostname or IP address of the Blue Iris server |
| Port | Textbox | Yes | 81 | HTTP port used to access the Blue Iris server |
| SSL | Toggle | Yes | Disabled | Whether SSL is enabled |
| Verify SSL | Toggle | Yes | Enabled | Whether to verify the SSL certificate |
| Username | Textbox | No | — | Username for Blue Iris |
| Password | Textbox | No | — | Password for Blue Iris |

---

# Integration Options

`Configuration → Integrations → Blue Iris → Options`

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| Log Level | Drop-down | Yes | Default | Sets integration logging level |
| Stream Type | Drop-down | Yes | H264 | Defines the stream type |
| Enable Camera Streaming | Toggle | Yes | False | Enables Home Assistant Stream component |
| Allowed Cameras | Multi-select | No | — | Controls which Blue Iris cameras are exposed as camera entities |
| Allowed Profiles | Multi-select | No | — | Controls which profiles are available in the Profile select |
| Allowed Schedules | Multi-select | No | — | Controls which schedules are available in the Schedule select |

---

# AI Label Mapping

`Configuration → Integrations → Blue Iris → Options → Second Page`

This page is only visible if at least one **Motion Sensor camera** is selected on the previous page.

| Field Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| Person Labels | Drop-down (multi) | No | `person` | Defines which model labels should be classified as **Person** |
| Vehicle Labels | Drop-down (multi) | No | `bicycle`, `car`, `motorcycle`, `bus`, `train`, `truck`, `boat`, `airplane` | Defines which model labels should be classified as **Vehicle** |
| Animal Labels | Drop-down (multi) | No | `bird`, `cat`, `dog`, `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe` | Defines which model labels should be classified as **Animal** |

Labels are **case insensitive but must match exactly**.

Example:

```text
bear → matches
polar-bear → does not match
```

---

# Entities and Components

## Binary Sensors

Camera-based sensors include:

- Motion (General, Person, Vehicle, Animal)
- Audio
- Connectivity
- DIO
- External

Server sensors:

- Alerts

## Last Motion Event Sensors

Each camera configured with **Motion Sensors** also provides a **Last Motion Event sensor**.

Example entity:

```text
sensor.driveway_last_motion_event
```

Example state:

```text
Person detected
```

Example attributes:

| Attribute | Description |
| --- | --- |
| `event_type` | Motion event type |
| `last_detection` | Timestamp of the most recent event |
| `memo` | Raw memo from Blue Iris |
| `labels` | AI labels detected |
| `matched_labels` | Labels matching configured AI categories |
| `snapshot_url` | Blue Iris still image URL |
| `stored_path` | Path to the locally saved snapshot, if one has been saved |

When a new event occurs, the stored snapshot path is cleared until a new snapshot is saved.

### Why Last Motion Event Sensors Matter

These sensors are designed to be automation-friendly and work especially well for notifications, camera-specific logic, and alarm-aware workflows.

If you want a ready-to-use notification setup based on these sensors, see the motion-focused blueprint below.

## Update Sensors

The **Server device** includes an **Update sensor** that allows Home Assistant to detect when a newer Blue Iris version is available.

This sensor can also trigger a Blue Iris update when supported.

## Camera Entity

Camera entities represent each selected Blue Iris camera.

Default state:

```text
Idle
```

## Profile and Schedule Selects

The **Server device** provides admin-only select entities for Blue Iris profile and schedule control.

- **Profile** select: changes the active Blue Iris profile.
- **Schedule** select: changes the active Blue Iris schedule.

The available choices are controlled by the **Allowed Profiles** and **Allowed Schedules** options.

## Hold Profile Changes Switch

The **Server device** also provides a **Hold Profile Changes** config switch.

This switch does not immediately call Blue Iris when toggled. Instead, it controls how future profile changes behave:

- When off, selecting a profile sends the profile change normally.
- When on, selecting a profile uses Blue Iris hold behavior so the selected profile is held instead of being overridden by the schedule.
  
---

# Services

## Latest Motion Event Snapshot

Fetch the latest snapshot for a camera and optionally save it locally.

| Field | Required | Description |
| --- | --- | --- |
| `entity_id` | Yes | Camera entity |
| `filename` | No | Optional filename stored under `<config>/www/blueiris/` |

If `filename` is omitted, the integration automatically uses:

```text
<camera_id>_latest_motion.jpg
```

Example:

```yaml
service: blueiris.latest_motion_event_snapshot
target:
  entity_id: camera.driveway
```

Saved file:

```text
<config>/www/blueiris/driveway_latest_motion.jpg
```

Accessible in Home Assistant as:

```text
/local/blueiris/driveway_latest_motion.jpg
```

## Trigger Camera

Triggers a camera or camera group manually.

## Move to Preset

Moves a PTZ camera to a configured preset.

## Reload

Reloads the integration without restarting Home Assistant.

---

# Blueprint

## Blue Iris - Last Motion Event Notifications

I strongly suggest checking out this blueprint if you want to see one way the last motion event sensor can be used.

The blueprint uses the integration’s:

- **Last Motion Event sensors**
- **camera entities**
- **latest motion event snapshot service**

to create alarm-aware and camera-specific motion notifications with optional mute support.

### What the Blueprint Adds

- Notifications from multiple Blue Iris `*_last_motion_event` sensors using one automation
- Filtering by motion `event_type` values such as:
  - `motion_person`
  - `motion_vehicle`
  - `motion_animal`
  - `motion_multi`
  - `motion`
- Camera-specific suppression by alarm state:
  - `armed_home`
  - `armed_away`
  - `armed_night`
  - `armed_vacation`
- Snapshot image support using the integration’s saved latest motion-event image
- Optional dynamic dashboard navigation per camera
- Optional mute action support using a helper and companion automations

### Install Blueprint

[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/kramttocs/ha-blueprints/main/Automations/blueiris-last-event-notifications.yaml)

### Full Blueprint Documentation

For full setup instructions, inputs, examples, and optional companion mute automations, see the blueprint documentation in the **ha-blueprints** repository:

- Blueprint source: [`Automations/blueiris-last-event-notifications.yaml`](https://github.com/kramttocs/ha-blueprints/blob/main/Automations/blueiris-last-event-notifications.yaml)
- Blueprint documentation: [`https://github.com/kramttocs/ha-blueprints`](https://github.com/kramttocs/ha-blueprints/tree/main)

### Notes

- The blueprint assumes the following naming relationship:
  - `sensor.<camera_object_id>_last_motion_event`
  - `camera.<camera_object_id>`
- The blueprint supports notifications with or without a locally saved snapshot image.
- If you use the optional mute action, follow the companion automation setup in the blueprint documentation.

---

# Example Automation

If you want a simple automation instead of the blueprint, here is a basic example that sends a notification when a motion event occurs and includes the latest snapshot. It's not setup to be generic but just an example.

```yaml
alias: Blue Iris - Driveway notification
mode: queued

trigger:
  - platform: state
    entity_id: sensor.driveway_last_motion_event

condition:
  - condition: template
    value_template: >
      {{ trigger.to_state.state not in ['unknown','unavailable','none','idle','No event'] }}

action:
  - service: blueiris.latest_motion_event_snapshot
    target:
      entity_id: camera.driveway

  - service: notify.mobile_app_your_phone
    data:
      title: "Blue Iris: Driveway"
      message: "{{ states('sensor.driveway_last_motion_event') }}"
      data:
        image: "/local/blueiris/driveway_latest_motion.jpg?v={{ now().timestamp() }}"
```

### Cache Busting

Adding a timestamp ensures the newest snapshot is always displayed:

```text
?v={{ now().timestamp() }}
```
