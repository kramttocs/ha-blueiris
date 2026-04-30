"""Blue Iris data update coordinator."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from json import JSONDecodeError
from collections.abc import Awaitable
from typing import Any


from homeassistant.components import mqtt
from homeassistant.components.mqtt import ReceiveMessage
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.blue_iris_api import BlueIrisApi, BlueIrisConfig
from .helpers.const import (
    AI_ANIMAL_MOTION,
    AI_PERSON_MOTION,
    AI_VEHICLE_MOTION,
    CONF_AI_ANIMAL_LABELS,
    CONF_AI_PERSON_LABELS,
    CONF_AI_VEHICLE_LABELS,
    CONF_ALLOWED_AUDIO_SENSOR,
    CONF_ALLOWED_CAMERA,
    CONF_ALLOWED_CONNECTIVITY_SENSOR,
    CONF_ALLOWED_DIO_SENSOR,
    CONF_ALLOWED_EXTERNAL_SENSOR,
    CONF_ALLOWED_MOTION_SENSOR,
    CONF_ALLOWED_PROFILE,
    CONF_ALLOWED_SCHEDULE,
    CONF_HOLD_PROFILE_CHANGES,
    CONF_STREAM_TYPE,
    CONF_SUPPORT_STREAM,
    DEFAULT_HOLD_PROFILE_CHANGES,
    DEFAULT_PORT,
    DEFAULT_QOS,
    DEFAULT_STREAM_TYPE,
    DOMAIN,
    MQTT_MESSAGE_TRIGGER,
    MQTT_MESSAGE_TYPE,
    MQTT_MESSAGE_VALUE_UNKNOWN,
    MQTT_ROOT_DEFAULT,
    MQTT_TOPIC_STATUS_SUFFIX,
    MQTT_TOPIC_SYSTEM_SEGMENT,
    MQTT_TYPE_TO_SENSOR_KEY,
    SCAN_INTERVAL,
    SENSOR_MOTION_NAME,
)
from .models.camera_data import CameraData
from .helpers.mqtt import mqtt_key, parse_topic, subscription_topic


_LOGGER = logging.getLogger(__name__)


def _looks_like_auth_failure(msg: str) -> bool:
    """Return True when an error message indicates an auth/session issue."""
    m = msg.lower()
    return (
        "invalid session" in m
        or "access denied" in m
        or "authorization" in m
        or "unauthorized" in m
    )


# Camera lists rarely change; refresh less frequently than status.
CAMLIST_REFRESH_INTERVAL = timedelta(minutes=10)
# Coalesce bursts of MQTT messages into a single HA state update.
MQTT_DEBOUNCE_SECONDS = 0.3
# Coalesce bursts of write actions into a single coordinator refresh.
WRITE_REFRESH_DEBOUNCE_SECONDS = 0.25


def _normalize_label_list(values: list[str] | None) -> list[str]:
    """Normalize user-provided label list: lowercase, strip, dedupe, preserve order."""
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        v2 = (v or "").strip().lower()
        if not v2 or v2 in seen:
            continue
        seen.add(v2)
        out.append(v2)
    return out


def _match_ai_categories(
    labels: set[str],
    person_allowed: set[str],
    vehicle_allowed: set[str],
    animal_allowed: set[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (person_matched, vehicle_matched, animal_matched, combined_matched).

    Exact-match semantics, stable (sorted) output lists.
    Single pass over labels for speed.
    """
    if not labels:
        return ([], [], [], [])

    p: list[str] = []
    v: list[str] = []
    a: list[str] = []

    for lab in labels:
        if lab in person_allowed:
            p.append(lab)
        if lab in vehicle_allowed:
            v.append(lab)
        if lab in animal_allowed:
            a.append(lab)

    if not (p or v or a):
        return ([], [], [], [])

    p.sort()
    v.sort()
    a.sort()
    combined = sorted(set(p).union(v, a))
    return (p, v, a, combined)


@dataclass(slots=True)
class MqttEventState:
    """Snapshot of MQTT-derived state for a single camera event type."""

    value: bool
    memo: str | None = None
    labels: list[str] | None = None
    matched_labels: list[str] | None = None
    last_detection: str | None = None


@dataclass(slots=True)
class CameraLastMotionEvent:
    """High-level latest motion event tracked per camera."""

    camera_id: str
    event_type: str
    state: str
    last_detection: str
    snapshot_url: str
    memo: str | None = None
    labels: list[str] | None = None
    matched_labels: list[str] | None = None
    stored_path: str | None = None


@dataclass(slots=True)
class BlueIrisData:
    """Coordinator snapshot containing API data, status, cameras, and MQTT state."""

    status: dict[str, Any]
    data: dict[str, Any]
    system_name: str | None
    server_version: str | None
    new_version: str | None
    cameras: dict[str, CameraData]  # keyed by camera id

    mqtt: dict[str, MqttEventState]  # keyed by mqtt_key(...)
    last_motion_events: dict[str, CameraLastMotionEvent]  # keyed by camera id

    base_url: str
    session_id: str | None


class BlueIrisDataUpdateCoordinator(DataUpdateCoordinator[BlueIrisData]):
    """Coordinator that is the single source of truth for this integration."""

    @property
    def mqtt_root(self) -> str:
        """Return the configured MQTT root topic segment."""
        return self._mqtt_root

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.hass = hass

        self._mqtt_debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=MQTT_DEBOUNCE_SECONDS,
            immediate=False,
            function=self._async_push_mqtt_update,
        )
        self._refresh_debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=WRITE_REFRESH_DEBOUNCE_SECONDS,
            immediate=False,
            function=self.async_request_refresh,
        )

        self._config = self._config_from_entry(entry)
        self.api = BlueIrisApi(hass, self._config)

        self._mqtt: dict[str, MqttEventState] = {}
        self._last_motion_events: dict[str, CameraLastMotionEvent] = {}

        self._mqtt_unsub: Any | None = None
        self._mqtt_root = MQTT_ROOT_DEFAULT
        self._mqtt_sub_topic: str | None = None

        # Cache AI label sets (exact-match, case-insensitive).
        self._ai_person_labels: set[str] = set()
        self._ai_vehicle_labels: set[str] = set()
        self._ai_animal_labels: set[str] = set()
        self._rebuild_ai_label_sets()

        # Write serialization + settle refresh to keep BI and HA in sync during rapid toggles.
        self._write_lock = asyncio.Lock()
        self._write_refresh_task: asyncio.Task | None = None
        self._last_write_monotonic: float = 0.0
        self._write_settle_seconds: float = 0.75

        self.consecutive_failures: int = 0
        self.auth_failures: int = 0
        self.last_success_time: datetime | None = None

        # Ensure we refresh camlist on the very first update.
        self._last_camlist_refresh = dt_util.utcnow() - CAMLIST_REFRESH_INTERVAL - timedelta(seconds=1)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )

    def _get_mqtt(self, key: str) -> MqttEventState:
        st = self._mqtt.get(key)
        if st is None:
            st = self._mqtt[key] = MqttEventState(value=False)
        return st

    def _set_mqtt(
        self,
        key: str,
        *,
        value: bool | None = None,
        memo: str | None = None,
        labels: list[str] | None = None,
        matched_labels: list[str] | None = None,
        ts: str | None = None,
    ) -> None:
        """Upsert a unified MQTT record for a key."""
        st = self._get_mqtt(key)

        if value is not None:
            st.value = value
        if memo is not None:
            st.memo = memo
        if labels is not None:
            st.labels = labels
        if matched_labels is not None:
            st.matched_labels = matched_labels
        if ts is not None:
            st.last_detection = ts

    def _clear_ai_motion_values(self, topic: str) -> None:
        """Clear memo-driven AI motion states for the supplied camera topic."""
        for t in (AI_PERSON_MOTION, AI_VEHICLE_MOTION, AI_ANIMAL_MOTION):
            self._set_mqtt(mqtt_key(topic, t), value=False)

    def _rebuild_ai_label_sets(self) -> None:
        """Rebuild normalized AI label lookup sets from the current config."""
        self._ai_person_labels = set(_normalize_label_list(getattr(self._config, "ai_person_labels", None)))
        self._ai_vehicle_labels = set(_normalize_label_list(getattr(self._config, "ai_vehicle_labels", None)))
        self._ai_animal_labels = set(_normalize_label_list(getattr(self._config, "ai_animal_labels", None)))

    def _set_ai_category(
        self,
        topic: str,
        category_key: str,
        *,
        memo: str,
        labels_list: list[str],
        matched: list[str],
        ts: str,
    ) -> None:
        k = mqtt_key(topic, category_key)
        self._set_mqtt(k, value=True, memo=memo, labels=labels_list, matched_labels=matched, ts=ts)

    def _still_image_url(self, camera_id: str) -> str:
        """Build the current still-image URL for a camera."""
        return self.api.still_image_url(camera_id)

    def get_last_motion_event(self, camera_id: str) -> CameraLastMotionEvent | None:
        """Return the latest tracked motion event for a camera, if any."""
        return self._last_motion_events.get(camera_id)

    def set_last_motion_event_stored_path(self, camera_id: str, stored_path: str | None) -> None:
        """Persist the most recent saved snapshot path for a camera event."""
        event = self._last_motion_events.get(camera_id)
        if event is None:
            return
        event.stored_path = stored_path
        if self.data is not None:
            self.async_set_updated_data(replace(self.data, last_motion_events=dict(self._last_motion_events)))

    def _record_last_motion_event(
        self,
        *,
        camera_id: str,
        memo: str,
        labels_list: list[str],
        combined: list[str],
        person_matched: list[str],
        vehicle_matched: list[str],
        animal_matched: list[str],
        ts: str,
    ) -> None:
        """Store a high-level per-camera latest motion event snapshot."""
        categories: list[str] = []
        if person_matched:
            categories.append("Person")
        if vehicle_matched:
            categories.append("Vehicle")
        if animal_matched:
            categories.append("Animal")
    
        if len(categories) == 1:
            state = f"{categories[0]} detected"
            event_type = f"motion_{categories[0].lower()}"
        elif categories:
            state = f"{', '.join(categories)} detected"
            event_type = "motion_multi"
        else:
            state = "Motion detected"
            event_type = "motion"
    
        self._last_motion_events[camera_id] = CameraLastMotionEvent(
            camera_id=camera_id,
            event_type=event_type,
            state=state,
            last_detection=ts,
            snapshot_url=self._still_image_url(camera_id),
            memo=memo or None,
            labels=labels_list or None,
            matched_labels=combined or None,
            stored_path=None,
        )

    async def async_fetch_camera_snapshot(self, camera_id: str) -> bytes | None:
        """Fetch the current still image bytes for a camera."""
        return await self.api.fetch_camera_image(camera_id)

    def update_entry(self, entry: ConfigEntry) -> None:
        """Update config when options change."""
        self.entry = entry
        self._config = self._config_from_entry(entry)
        self.api.update_config(self._config)
        self._rebuild_ai_label_sets()

    def _cancel_write_refresh_task(self) -> None:
        """Cancel any pending delayed refresh created after a write operation."""
        task = self._write_refresh_task
        if task and not task.done():
            task.cancel()
        self._write_refresh_task = None

    async def _async_refresh_after_settle(self) -> None:
        """Wait briefly after a write, then request a coordinator refresh."""
        try:
            while True:
                elapsed = time.monotonic() - self._last_write_monotonic
                remaining = self._write_settle_seconds - elapsed
                if remaining <= 0:
                    break
                await asyncio.sleep(min(remaining, 0.25))
            await self.async_request_refresh()
        except asyncio.CancelledError:
            return

    async def async_schedule_refresh_after_write(self) -> None:
        """Schedule a delayed refresh after a write has been issued to Blue Iris."""
        self._last_write_monotonic = time.monotonic()
        self._cancel_write_refresh_task()
        self._write_refresh_task = self.hass.async_create_task(
            self._async_refresh_after_settle(),
            name=f"{DOMAIN}_write_settle_refresh",
        )

    async def async_write_and_refresh(self, write_awaitable: Awaitable[Any]) -> Any:
        """Serialize writes and refresh once after the last write settles.

        Design notes:
            - _write_lock ensures only one write is in-flight at a time, preventing
            race conditions when the UI changes settings rapidly.
            - async_schedule_refresh_after_write() is called inside the lock so
            _last_write_monotonic is updated atomically after the write completes.
            - The actual settle-wait task runs outside the lock. This is intentional;
            the lock should not be held during the settle sleep.
            - If another write arrives before the settle timer fires, the previous
            timer is cancelled and the new write schedules a fresh one, coalescing
            rapid writes into a single follow-up refresh.
        """
        async with self._write_lock:
            result = await write_awaitable
            await self.async_schedule_refresh_after_write()
            return result

    async def async_schedule_refresh(self) -> None:
        """Request a coordinator refresh without waiting for it to complete."""
        await self._refresh_debouncer.async_call()

    async def async_shutdown(self) -> None:
        """Unsubscribe MQTT and close API resources during integration unload."""
        self._cancel_write_refresh_task()
        self._mqtt_debouncer.async_shutdown()
        self._refresh_debouncer.async_shutdown()

        if self._mqtt_unsub is not None:
            self._mqtt_unsub()
            self._mqtt_unsub = None
            self._mqtt_sub_topic = None

        await self.api.async_close()

    async def _ensure_mqtt_subscription(self) -> None:
        """Create the MQTT subscription when MQTT support is available and configured."""
        if "mqtt" not in self.hass.config.components:
            _LOGGER.debug("MQTT not available, skipping Blue Iris MQTT subscription")
            return

        try:
            server = (self.api.system_name or "").strip()
            if not server:
                _LOGGER.debug("MQTT server name unknown; skipping subscription until known")
                return

            topic = subscription_topic(self.mqtt_root, server, suffix=MQTT_TOPIC_STATUS_SUFFIX)

            if self._mqtt_unsub is not None and self._mqtt_sub_topic == topic:
                return

            if self._mqtt_unsub is not None:
                self._mqtt_unsub()
                self._mqtt_unsub = None
                self._mqtt_sub_topic = None

            self._mqtt_sub_topic = topic
            self._mqtt_unsub = await mqtt.async_subscribe(
                self.hass,
                topic,
                self.process_mqtt_message,
                DEFAULT_QOS,
            )
            _LOGGER.debug("Subscribed to MQTT topic %s", topic)

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to subscribe to MQTT: %s", err)
            self._mqtt_unsub = None
            self._mqtt_sub_topic = None

    async def _async_process_mqtt_message(self, topic: str, payload: dict[str, Any]) -> None:
        """Process an MQTT message on the event loop."""
        parsed = parse_topic(topic)
        if parsed is None:
            return
    
        if not self._mqtt_matches_expected_server(parsed.server):
            return
    
        cam_id = parsed.camera_id  # "System" or camera id
        is_system = self._mqtt_is_system_topic(cam_id)
    
        # Some system payloads come in a shorthand form (no explicit type/trigger).
        if is_system and self._mqtt_is_system_refresh_shortcut(payload):
            await self.async_schedule_refresh()
            return
    
        event_type_l, trigger_u = self._mqtt_extract_type_and_trigger(payload)
        sensor_key, is_motion = self._mqtt_resolve_sensor_key(event_type_l)
        if not sensor_key:
            return
    
        value = self._mqtt_trigger_to_bool(trigger_u)
        if value is None:
            return
    
        # Always update the sensor state keyed off topic+sensor_key.
        self._set_mqtt(mqtt_key(topic, sensor_key), value=value)
    
        if is_motion:
            await self._mqtt_handle_motion_message(
                topic=topic,
                cam_id=cam_id,
                payload=payload,
                is_system=is_system,
                value=value,
            )
        else:
            self._mqtt_log_non_motion(topic=topic, cam_id=cam_id, sensor_key=sensor_key, value=value, payload=payload)
    
        if is_system and ("profile" in payload or "schedule" in payload):
            await self.async_schedule_refresh()
    
        await self._mqtt_debouncer.async_call()
    
    def _mqtt_matches_expected_server(self, server_in_topic: str) -> bool:
        """Return True if the topic server matches the expected BI system name."""
        expected_server = (self.api.system_name or "").strip()
        if not expected_server:
            return True
        return server_in_topic.strip().lower() == expected_server.lower()
    
    @staticmethod
    def _mqtt_is_system_topic(cam_id: str) -> bool:
        return str(cam_id).strip().lower() == MQTT_TOPIC_SYSTEM_SEGMENT.lower()
    
    @staticmethod
    def _mqtt_is_system_refresh_shortcut(payload: dict[str, Any]) -> bool:
        """System messages may omit type/trigger when only profile/schedule changed."""
        if not ("profile" in payload or "schedule" in payload):
            return False
        return MQTT_MESSAGE_TYPE not in payload and MQTT_MESSAGE_TRIGGER not in payload
    
    @staticmethod
    def _mqtt_extract_type_and_trigger(payload: dict[str, Any]) -> tuple[str, str]:
        event_type_raw = payload.get(MQTT_MESSAGE_TYPE, MQTT_MESSAGE_VALUE_UNKNOWN)
        trigger_raw = payload.get(MQTT_MESSAGE_TRIGGER, MQTT_MESSAGE_VALUE_UNKNOWN)
        event_type_l = str(event_type_raw).strip().lower()
        trigger_u = str(trigger_raw).strip().upper()
        return event_type_l, trigger_u
    
    @staticmethod
    def _mqtt_resolve_sensor_key(event_type_l: str) -> tuple[str, bool]:
        """Resolve payload type -> internal sensor key; returns (sensor_key, is_motion)."""
        is_motion = str(event_type_l).startswith("motion")
        if is_motion:
            return SENSOR_MOTION_NAME.lower(), True
    
        sensor_key = str(MQTT_TYPE_TO_SENSOR_KEY.get(event_type_l, "")).strip().lower()
        if not sensor_key:
            return "", False
        return sensor_key, False
    
    @staticmethod
    def _mqtt_trigger_to_bool(trigger_u: str) -> bool | None:
        if trigger_u == "ON":
            return True
        if trigger_u == "OFF":
            return False
        return None
    
    def _mqtt_log_non_motion(
        self,
        *,
        topic: str,
        cam_id: str,
        sensor_key: str,
        value: bool,
        payload: dict[str, Any],
    ) -> None:
        _LOGGER.debug(
            "BI MQTT: topic=%s cam_id=%s event_type=%s value=%s payload_keys=%s",
            topic,
            cam_id,
            sensor_key,
            value,
            sorted(payload.keys()),
        )
    
    async def _mqtt_handle_motion_message(
        self,
        *,
        topic: str,
        cam_id: str,
        payload: dict[str, Any],
        is_system: bool,
        value: bool,
    ) -> None:
        """Handle Motion / Motion_A / Motion_B, including memo-driven AI sensors."""
        # AI memo-driven motion sensors (camera topics only)
        if is_system:
            return
    
        memo = str(payload.get("memo") or "").strip()
        motion_key = SENSOR_MOTION_NAME.lower()
        motion_k = mqtt_key(topic, motion_key)
    
        if not value:
            # Turn off AI sensors, but KEEP last memo/labels/etc (keep-last behavior).
            self._clear_ai_motion_values(topic)
            return
    
        labels_set = self._parse_memo_labels(memo)
        labels_list = sorted(labels_set)
        ts = dt_util.utcnow().isoformat()
    
        person_matched, vehicle_matched, animal_matched, combined = _match_ai_categories(
            labels_set,
            self._ai_person_labels,
            self._ai_vehicle_labels,
            self._ai_animal_labels,
        )
    
        # Always store memo/labels on generic Motion sensor when motion turns ON.
        self._set_mqtt(
            motion_k,
            value=True,  # motion is ON
            memo=memo,
            labels=labels_list,
            matched_labels=combined,
            ts=ts,
        )
    
        _LOGGER.debug(
            "BI MQTT: topic=%s cam_id=%s event_type=%s value=%s memo=%r labels=%s matched=%s ts=%s",
            topic,
            cam_id,
            motion_key,
            value,
            memo,
            labels_list,
            combined,
            ts,
        )
    
        # Clear category states on every motion-ON update so they don't stay True
        # across consecutive "on" messages when the new memo no longer matches.
        self._clear_ai_motion_values(topic)
    
        if person_matched:
            self._set_ai_category(
                topic,
                AI_PERSON_MOTION,
                memo=memo,
                labels_list=labels_list,
                matched=person_matched,
                ts=ts,
            )
        if vehicle_matched:
            self._set_ai_category(
                topic,
                AI_VEHICLE_MOTION,
                memo=memo,
                labels_list=labels_list,
                matched=vehicle_matched,
                ts=ts,
            )
        if animal_matched:
            self._set_ai_category(
                topic,
                AI_ANIMAL_MOTION,
                memo=memo,
                labels_list=labels_list,
                matched=animal_matched,
                ts=ts,
            )

        self._record_last_motion_event(
            camera_id=cam_id,
            memo=memo,
            labels_list=labels_list,
            combined=combined,
            person_matched=person_matched,
            vehicle_matched=vehicle_matched,
            animal_matched=animal_matched,
            ts=ts,
        )
            
    def process_mqtt_message(self, message: ReceiveMessage) -> None:
        """Decode an MQTT message and schedule async processing."""
        raw = message.payload
        if not raw:
            return

        text = (
            raw.decode("utf-8", errors="replace").strip()
            if isinstance(raw, (bytes, bytearray))
            else str(raw).strip()
        )
        if not text:
            return

        try:
            payload = json.loads(text)
        except JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON MQTT payload topic=%s payload=%r", message.topic, text)
            return
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed decoding MQTT payload topic=%s payload=%r", message.topic, text)
            return

        if not isinstance(payload, dict):
            _LOGGER.debug("Ignoring non-dict JSON payload topic=%s payload=%r", message.topic, payload)
            return

        self.hass.async_create_task(
            self._async_process_mqtt_message(message.topic, payload),
            name=f"{DOMAIN}_mqtt_message",
        )

    async def _async_push_mqtt_update(self) -> None:
        """Push updated MQTT state into coordinator data without polling the API."""
        if self.data is None:
            return

        self.async_set_updated_data(
            replace(
                self.data,
                mqtt=dict(self._mqtt),
                last_motion_events=dict(self._last_motion_events),
            )
        )

    @staticmethod
    def _config_from_entry(entry: ConfigEntry) -> BlueIrisConfig:
        """Build config from entry, ensuring option lists default to [].

        Fixes:
        - Use DEFAULT_PORT (not hardcoded 80)
        - Default allowed_* option lists to [] (not None)
        """
        data = entry.data
        options = entry.options

        return BlueIrisConfig(
            host=str(data.get(CONF_HOST, "")).strip(),
            port=int(data.get(CONF_PORT, DEFAULT_PORT)),
            ssl=bool(data.get(CONF_SSL, False)),
            verify_ssl=bool(data.get(CONF_VERIFY_SSL, False)),
            username=str(data.get(CONF_USERNAME, "")),
            password=str(data.get(CONF_PASSWORD, "")),
            stream_type=str(options.get(CONF_STREAM_TYPE, DEFAULT_STREAM_TYPE)),
            support_stream=bool(options.get(CONF_SUPPORT_STREAM, False)),
            hold_profile_changes=bool(options.get(CONF_HOLD_PROFILE_CHANGES, DEFAULT_HOLD_PROFILE_CHANGES)),
            allowed_camera=options.get(CONF_ALLOWED_CAMERA, []),
            allowed_profile=options.get(CONF_ALLOWED_PROFILE, []),
            allowed_schedule=options.get(CONF_ALLOWED_SCHEDULE, []),
            allowed_motion_sensor=options.get(CONF_ALLOWED_MOTION_SENSOR, []),
            allowed_audio_sensor=options.get(CONF_ALLOWED_AUDIO_SENSOR, []),
            allowed_connectivity_sensor=options.get(CONF_ALLOWED_CONNECTIVITY_SENSOR, []),
            allowed_dio_sensor=options.get(CONF_ALLOWED_DIO_SENSOR, []),
            allowed_external_sensor=options.get(CONF_ALLOWED_EXTERNAL_SENSOR, []),
            ai_person_labels=_normalize_label_list(options.get(CONF_AI_PERSON_LABELS)),
            ai_vehicle_labels=_normalize_label_list(options.get(CONF_AI_VEHICLE_LABELS)),
            ai_animal_labels=_normalize_label_list(options.get(CONF_AI_ANIMAL_LABELS)),
        )

    @staticmethod
    def _parse_memo_labels(memo: str) -> set[str]:
        """Return lowercased label tokens found in memo string (exact-match ready)."""
        if not memo:
            return set()

        memo_l = memo.strip().lower().replace("-", "_")
        memo_l = re.sub(r"[,\|;/]+", " ", memo_l)

        labels: set[str] = set()

        for m in re.finditer(r"([a-z_][a-z0-9_]*)\s*[:=]\s*([0-9.]+%?)?", memo_l):
            labels.add(m.group(1))

        for m in re.finditer(r"([a-z_][a-z0-9_]*)\s*\(\s*[0-9.]+%?\s*\)", memo_l):
            labels.add(m.group(1))

        for token in re.split(r"\s+", memo_l):
            token = token.strip().strip("()[]{}<>\"'")
            if not token:
                continue
            if re.fullmatch(r"[0-9.]+%?", token):
                continue
            if re.fullmatch(r"[a-z_][a-z0-9_]*", token):
                labels.add(token)

        return labels

    async def _async_update_data(self) -> BlueIrisData:
        """Fetch data from Blue Iris."""
        try:
            try:
                status = await self.api.fetch_status()
            except Exception as err:
                _LOGGER.warning("Blue Iris status fetch failed (%r); retrying once...", err)
                await asyncio.sleep(0.5)
                try:
                    status = await self.api.fetch_status()
                except Exception as err2:
                    raise UpdateFailed(f"Blue Iris status fetch failed after retry: {err2}") from err2

            await self._ensure_mqtt_subscription()

            now = dt_util.utcnow()
            needs_camlist = (self.data is None) or (not self.data.cameras) or (
                now - self._last_camlist_refresh > CAMLIST_REFRESH_INTERVAL
            )

            if needs_camlist:
                camlist = await self.api.fetch_camlist()
                self._last_camlist_refresh = now
                cameras = {c.id: c for c in camlist}
            else:
                cameras = dict(self.data.cameras)

            login_data = self.api.data or {}
            system_name = self.api.system_name

            server_version = None
            new_version = None
            if isinstance(login_data, dict):
                server_version = login_data.get("version")
                new_version = login_data.get("newversion")

            self.consecutive_failures = 0
            self.auth_failures = 0
            self.last_success_time = dt_util.utcnow()

            return BlueIrisData(
                status=status or {},
                data=login_data,
                system_name=system_name,
                server_version=server_version,
                new_version=new_version,
                cameras=cameras,
                mqtt=self._mqtt,
                last_motion_events=dict(self._last_motion_events),
                base_url=self.api.base_url,
                session_id=self.api.session_id,
            )

        except UpdateFailed as err:
            self.consecutive_failures += 1
            msg = str(err)
            if _looks_like_auth_failure(msg):
                self.auth_failures += 1
            raise

        except Exception as err:
            self.consecutive_failures += 1
            msg = str(err)
            if _looks_like_auth_failure(msg):
                self.auth_failures += 1
            raise UpdateFailed(str(err)) from err
