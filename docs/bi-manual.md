# Blue Iris Home Assistant Manual

## Troubleshooting

> \[!TIP\] Enable **Debug** as the log level in the integration
> configuration when troubleshooting issues.

Submit a **GitHub issue** with logs
and details.

------------------------------------------------------------------------

## User

Best practice is to create a **separate Administrator
user** for Home Assistant and limit access to **LAN only**.

![Blue Iris Edit
User](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/edit_user.png)

------------------------------------------------------------------------

## Web Server

Enable the **Blue Iris Web Server**.

Select the **`Advanced...`** button to proceed to the next step.

Defaults are fine:

![Blue Iris Web Server
Advanced](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/web_server_advanced.png)

Configure the **Encoding settings**:

-   **Video:** `H.264`
-   **Audio:** `AAC`
-   **Resize output frame:** `1920 x 1080`

![Blue Iris Encoder
Options](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/web_server_encoder.png)

------------------------------------------------------------------------

# MQTT

To support the **MQTT binary sensors** for cameras, additional
configuration is required on **both Home Assistant and Blue Iris**.

1.  In your **MQTT broker**, create a user for **Blue Iris**
2.  Open **Blue Iris Settings → Digital IO and IoT**
3.  Go to **MQTT**
4.  Enter the host, port, username, and password

> \[!IMPORTANT\] The **ClientID must be one of the following formats**.

    BlueIris/[Your BI System Name]

or

    BlueIris/BlueIris

Example:

If your **Blue Iris server name** (defined on the **About tab**) is
`Home`, your MQTT settings may look like this:

![Blue Iris Edit MQTT
Server](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/edit_mqtt_server.png)

------------------------------------------------------------------------

## Actions

Blue Iris allows MQTT messages to be sent from many locations.

> \[!NOTE\] No matter where the action is configured the topic must
> follow this pattern.

    BlueIris/&SERVER/['System' or &CAM]/Status

------------------------------------------------------------------------

### Profiles and Schedules

The integration polls Blue Iris for updates.

-   **Server status** (profiles and schedules) every **25 seconds**
-   **Camera list and details** every **10 minutes**

If you want profile or schedule changes made in Blue Iris to appear **immediately** in Home Assistant, use an MQTT action.

Go to:

    Blue Iris Settings → Profiles

or

    Blue Iris Settings → Schedules

For the **On Change** option add an **MQTT Action**.

Example:

    Topic - BlueIris/&SERVER/System/Status
    Payload - { "profile": "&PROFILE"}

or

    Topic - BlueIris/&SERVER/System/Status
    Payload - { "schedule": "&SCHEDULE"}


This message causes the integration to **immediately refresh the Blue
Iris status**.

![Blue Iris MQTT Profile
Action](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/mqtt_profile_action.png)

------------------------------------------------------------------------

### Cameras

For each camera you wish to monitor go to:

    Camera Properties → Alerts

> \[!TIP\] This page has extensive configuration options. Review the
> **official Blue Iris help manual** for detailed explanations.

Go to **On Alert** in the **Actions** section and add an **MQTT
action**.

![Blue Iris MQTT Alert
Action](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/mqtt_alert_action.png)

Example:

    Topic - BlueIris/&SERVER/&CAM/Status
    Payload - { "type": "&TYPE", "trigger": "ON", "memo": "&MEMO" }

  `&TYPE`   Determines Motion, DIO, External, or Audio
  
  `&MEMO`   Used for AI labels such as Person, Animal, or Vehicle

To turn sensors **off**, configure a similar action under **On Reset**.

![Blue Iris MQTT Alert Action
Off](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/mqtt_alert_action_off.png)

    Topic - BlueIris/&SERVER/&CAM/Status
    Payload - { "type": "&TYPE", "trigger": "OFF" }

> \[!WARNING\] Triggering the camera **manually** in Blue Iris sends a
> different `&TYPE` and **will not trigger the motion sensor**. Motion
> must be detected by the camera.

------------------------------------------------------------------------

### Watchdog (Connectivity)

Open:

    Camera Properties → Watchdog

Configure the settings to suit your needs.

For **On Loss**, add an MQTT action.

![Blue Iris MQTT Connectivity Action
Off](https://github.com/kramttocs/ha-blueiris/blob/main/docs/images/mqtt_connectivity_action_off.png)

    Topic - BlueIris/&SERVER/&CAM/Status
    Payload - { "type": "Connectivity", "trigger": "OFF" }

For **On Restore**, use:

    { "type": "Connectivity", "trigger": "ON" }
