# Blue Iris NVR

![HomeAssistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-blue.svg)
![Maintenance](https://img.shields.io/badge/Maintained-Yes-brightgreen.svg)

Home Assistant integration for **Blue Iris Video Security Software**.

This integration allows Home Assistant to interact with your Blue Iris
server, providing cameras, sensors, profile control, and automation
support.

📄
[Changelog](https://github.com/kramttocs/ha-blueiris/blob/main/CHANGELOG.md)

📄
Please read: [Manual](https://github.com/kramttocs/ha-blueiris/blob/main/docs/bi-manual.md)


------------------------------------------------------------------------


# Table of Contents

-   [Credit](#credit)
-   [Installation and Setup](#installation-and-setup)
    -   [Requirements](#requirements)
    -   [Installation via HACS](#installation-via-hacs)
-   [Integration Configuration](#integration-configuration)
    -   [Basic Setup](#basic-setup)
-   [Integration Options](#integration-options)
-   [AI Label Mapping](#ai-label-mapping)
-   [Entities and Components](#entities-and-components)
-   [Services](#services)

------------------------------------------------------------------------

# Credit

This integration builds upon the excellent work originally created by
**elad-bar**.

As he no longer uses Blue Iris, he granted permission to
reuse ideas and concepts from the original project. 

------------------------------------------------------------------------

# Installation and Setup

## Requirements

-   A **Blue Iris server** accessible from Home Assistant
-   A **user account** configured in Blue Iris
-   A **Server Name** configured in Blue Iris settings
-   To control **Profiles**, the user must have **Admin permissions**
-   **MQTT integration (optional)** for real-time event updates

------------------------------------------------------------------------

## Installation via HACS

1.  Open **HACS**
2.  Search for **Blue Iris NVR**
3.  Install the integration
4.  Restart Home Assistant if prompted

------------------------------------------------------------------------

# Integration Configuration

## Basic Setup

`Configuration → Integrations → Add Integration → BlueIris NVR`

| Field | Type | Required | Default | Description |
|------|------|------|------|------|
| Host | Textbox | Yes | None | Hostname or IP address of the Blue Iris server |
| Port | Textbox | Yes | 81 | HTTP port used to access the Blue Iris server |
| SSL | Toggle | Yes | Disabled | Whether SSL is enabled |
| Verify SSL | Toggle | Yes | Enabled | Whether to verify the SSL certificate |
| Username | Textbox | No | — | Username for Blue Iris |
| Password | Textbox | No | — | Password for Blue Iris |

------------------------------------------------------------------------

## Integration Options

`Configuration → Integrations → BlueIris NVR → Options`

| Field | Type | Required | Default | Description |
|------|------|------|------|------|
| Log Level | Drop-down | Yes | Default | Sets integration logging level |
| Stream Type | Drop-down | Yes | H264 | Defines the stream type |
| Enable Camera Streaming | Toggle | Yes | False | Enables Home Assistant Stream component |
| Hold Profile Change | Toggle | Yes | True | Determines if profile changes are held |
| Allowed Cameras | Multi-select | No | — | Creates camera entities |
| Profile Switches | Multi-select | No | — | Creates profile switches |
| Schedule Switches | Multi-select | No | — | Creates schedule switches |


------------------------------------------------------------------------

## AI Label Mapping

`Configuration → Integrations → BlueIris NVR → Options → Second Page`

This page is only visible if at least one **Motion Sensor camera** is selected on the previous page.

| Field Name | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| Person Labels | Drop-down (multi) | No | `person` | Defines which model labels should be classified as **Person** |
| Vehicle Labels | Drop-down (multi) | No | `bicycle`, `car`, `motorcycle`, `bus`, `train`, `truck`, `boat`, `airplane` | Defines which model labels should be classified as **Vehicle** |
| Animal Labels | Drop-down (multi) | No | `bird`, `cat`, `dog`, `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe` | Defines which model labels should be classified as **Animal** |

Labels are **case insensitive but must match exactly**.

Example:

    bear → matches
    polar-bear → does not match

------------------------------------------------------------------------

# Entities and Components

## Binary Sensors

Camera-based sensors include:

-   Motion (General, Person, Vehicle, Animal)
-   Audio
-   Connectivity
-   DIO
-   External

Server sensors:

-   Alerts

------------------------------------------------------------------------

## Update Sensors

Server sensors:

-   The Server device provides an Update sensor with the ability to request Blue Iris to perform an update to the latest version if available

------------------------------------------------------------------------

## Camera Entity

Camera entities represent each selected Blue Iris camera.

Default state:

    Idle

------------------------------------------------------------------------

## Profile Switches

Each selected profile creates a **switch under the Server device**.

Only **one profile switch can be active at a time**.

Behavior when turning a profile **off**:

-   Turning off **Profile 1** activates **Profile 0**
-   Turning off **any other profile** activates **Profile 1**

------------------------------------------------------------------------

# Services

## Trigger Camera

Triggers a camera or camera group manually.

## Move to Preset

Moves a PTZ camera to a configured preset.

## Reload

Reloads the integration without restarting Home Assistant.
