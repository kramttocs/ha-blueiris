"""Config flow for Blue Iris."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)

from .api.blue_iris_api import BlueIrisApi, BlueIrisConfig
from .helpers.const import (
    DOMAIN,
    DEFAULT_NAME,
    DEFAULT_PORT,
    CONF_LOG_LEVEL,
    LOG_LEVEL_DEFAULT,
    CONF_ALLOWED_CAMERA,
    CONF_ALLOWED_PROFILE,
    CONF_ALLOWED_SCHEDULE,
    CONF_ALLOWED_MOTION_SENSOR,
    CONF_ALLOWED_AUDIO_SENSOR,
    CONF_ALLOWED_CONNECTIVITY_SENSOR,
    CONF_ALLOWED_DIO_SENSOR,
    CONF_ALLOWED_EXTERNAL_SENSOR,
    CONF_AI_PERSON_LABELS,
    CONF_AI_VEHICLE_LABELS,
    CONF_AI_ANIMAL_LABELS,
    DEFAULT_PERSON_LABELS,
    DEFAULT_VEHICLE_LABELS,
    DEFAULT_ANIMAL_LABELS,
    CONF_STREAM_TYPE,
    DEFAULT_STREAM_TYPE,
    STREAM_TYPE_H264,
    STREAM_TYPE_MJPG,
    CONF_SUPPORT_STREAM,
    CONF_HOLD_PROFILE_CHANGES,
    DEFAULT_HOLD_PROFILE_CHANGES,
    BI_CAMERA_TYPE_GROUP,
    BI_CAMERA_TYPE_SYSTEM,
    BI_CAMERA_TYPE_GENERIC,
    AI_LABELS_HELP
)

_LOGGER = logging.getLogger(__name__)


USER_STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=65535,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_VERIFY_SSL, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_USERNAME, default=""): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


def _is_filtered_camera(cam) -> bool:
    try:
        return int(getattr(cam, "type", 0)) in [
            BI_CAMERA_TYPE_GROUP,
            BI_CAMERA_TYPE_SYSTEM,
            BI_CAMERA_TYPE_GENERIC,
        ]
    except (TypeError, ValueError):
        return False


def _unique_id(host: str, port: int, ssl: bool) -> str:
    return f"{host}:{port}:{int(bool(ssl))}"


def _build_settings_schema(
    *,
    cached_lists: dict[str, Any],
    defaults: dict[str, Any],
) -> vol.Schema:
    """Build the common settings schema used for setup 'select' and options 'init'.

    AI labels are intentionally excluded; they have their own step(s).
    """
    schema: dict[Any, Any] = {
        vol.Required(CONF_LOG_LEVEL, default=defaults[CONF_LOG_LEVEL]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=LOG_LEVEL_DEFAULT, label="default"),
                    selector.SelectOptionDict(value="debug", label="debug"),
                    selector.SelectOptionDict(value="info", label="info"),
                    selector.SelectOptionDict(value="warning", label="warning"),
                    selector.SelectOptionDict(value="error", label="error"),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_STREAM_TYPE, default=defaults[CONF_STREAM_TYPE]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=STREAM_TYPE_H264, label=STREAM_TYPE_H264),
                    selector.SelectOptionDict(value=STREAM_TYPE_MJPG, label=STREAM_TYPE_MJPG),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_SUPPORT_STREAM, default=defaults[CONF_SUPPORT_STREAM]): selector.BooleanSelector(),
        vol.Optional(CONF_HOLD_PROFILE_CHANGES, default=defaults[CONF_HOLD_PROFILE_CHANGES]): selector.BooleanSelector(),
        vol.Optional(CONF_ALLOWED_CAMERA, default=defaults[CONF_ALLOWED_CAMERA]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_all", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_PROFILE, default=defaults[CONF_ALLOWED_PROFILE]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get(CONF_ALLOWED_PROFILE, []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_SCHEDULE, default=defaults[CONF_ALLOWED_SCHEDULE]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get(CONF_ALLOWED_SCHEDULE, []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_MOTION_SENSOR, default=defaults[CONF_ALLOWED_MOTION_SENSOR]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_filtered", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_AUDIO_SENSOR, default=defaults[CONF_ALLOWED_AUDIO_SENSOR]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_filtered", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_ALLOWED_CONNECTIVITY_SENSOR, default=defaults[CONF_ALLOWED_CONNECTIVITY_SENSOR]
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_filtered", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_DIO_SENSOR, default=defaults[CONF_ALLOWED_DIO_SENSOR]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_filtered", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_ALLOWED_EXTERNAL_SENSOR, default=defaults[CONF_ALLOWED_EXTERNAL_SENSOR]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=cached_lists.get("camera_filtered", []),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }

    return vol.Schema(schema)


def _dedupe_normalize_label_list(items: list[str] | None) -> list[str]:
    """Lowercase + strip + dedupe while preserving order."""
    if not items:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in items:
        v2 = (v or "").strip().lower()
        if not v2 or v2 in seen:
            continue
        seen.add(v2)
        out.append(v2)
    return out


def _ai_label_selector() -> selector.SelectSelector:
    """Multi-select with custom values (chip/dropdown style)."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[],
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


class BlueIrisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Blue Iris."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cached_lists: dict[str, list[selector.SelectOptionDict]] = {}
        self._pending_options: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return BlueIrisOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First step: connection/auth details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = cv.port(user_input[CONF_PORT])
            ssl = bool(user_input.get(CONF_SSL, False))

            await self.async_set_unique_id(_unique_id(host, port, ssl))
            self._abort_if_unique_id_configured()

            cfg = BlueIrisConfig(
                host=host,
                port=port,
                ssl=ssl,
                verify_ssl=bool(user_input.get(CONF_VERIFY_SSL, True)),
                username=str(user_input.get(CONF_USERNAME, "")),
                password=str(user_input.get(CONF_PASSWORD, "")),
                stream_type=DEFAULT_STREAM_TYPE,
            )
            api = BlueIrisApi(self.hass, cfg)
            try:
                await api.async_update()

                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SSL: ssl,
                    CONF_VERIFY_SSL: cfg.verify_ssl,
                    CONF_USERNAME: cfg.username,
                    CONF_PASSWORD: cfg.password,
                }

                return await self.async_step_select()

            except Exception:
                _LOGGER.exception("Failed to connect to Blue Iris during config flow")
                errors["base"] = "cannot_connect"
            finally:
                try:
                    await api.async_close()
                except Exception:
                    pass

        return self.async_show_form(step_id="user", data_schema=USER_STEP_SCHEMA, errors=errors)

    async def async_step_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Second step: general selectors during initial setup (no AI label mapping here)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._pending_options = dict(user_input)

            allowed_motion = self._pending_options.get(CONF_ALLOWED_MOTION_SENSOR, [])
            if allowed_motion:
                return await self.async_step_ai_labels_setup()

            title = DEFAULT_NAME
            return self.async_create_entry(title=title, data=self._data, options=self._pending_options)

        api = None
        try:
            cfg = BlueIrisConfig(
                host=str(self._data.get(CONF_HOST, "")).strip(),
                port=int(self._data.get(CONF_PORT, DEFAULT_PORT)),
                ssl=bool(self._data.get(CONF_SSL, False)),
                verify_ssl=bool(self._data.get(CONF_VERIFY_SSL, True)),
                username=str(self._data.get(CONF_USERNAME, "")),
                password=str(self._data.get(CONF_PASSWORD, "")),
                stream_type=DEFAULT_STREAM_TYPE,
            )
            api = BlueIrisApi(self.hass, cfg)
            await api.async_update()

            camera_opts = [selector.SelectOptionDict(value=c.id, label=c.name) for c in api.camera_list]
            camera_opts_filtered = [
                selector.SelectOptionDict(value=c.id, label=c.name)
                for c in api.camera_list
                if not _is_filtered_camera(c)
            ]

            profiles = api.data.get("profiles", []) or []
            profile_opts = [selector.SelectOptionDict(value=str(idx), label=str(name)) for idx, name in enumerate(profiles)]

            schedules = api.data.get("schedules", []) or []
            schedule_opts = [
                selector.SelectOptionDict(value=str(idx), label=str(name)) for idx, name in enumerate(schedules)
            ]

            self._cached_lists = {
                "camera_all": camera_opts,
                "camera_filtered": camera_opts_filtered,
                CONF_ALLOWED_PROFILE: profile_opts,
                CONF_ALLOWED_SCHEDULE: schedule_opts,
            }

        except Exception:
            _LOGGER.debug("Failed to fetch lists for config flow setup step", exc_info=True)
            self._cached_lists = {
                "camera_all": [],
                "camera_filtered": [],
                CONF_ALLOWED_PROFILE: [],
                CONF_ALLOWED_SCHEDULE: [],
            }
        finally:
            try:
                if api is not None:
                    await api.async_close()
            except Exception:
                pass

        defaults = {
            CONF_LOG_LEVEL: LOG_LEVEL_DEFAULT,
            CONF_STREAM_TYPE: DEFAULT_STREAM_TYPE,
            CONF_SUPPORT_STREAM: False,
            CONF_HOLD_PROFILE_CHANGES: DEFAULT_HOLD_PROFILE_CHANGES,
            CONF_ALLOWED_CAMERA: [],
            CONF_ALLOWED_PROFILE: [],
            CONF_ALLOWED_SCHEDULE: [],
            CONF_ALLOWED_MOTION_SENSOR: [],
            CONF_ALLOWED_AUDIO_SENSOR: [],
            CONF_ALLOWED_CONNECTIVITY_SENSOR: [],
            CONF_ALLOWED_DIO_SENSOR: [],
            CONF_ALLOWED_EXTERNAL_SENSOR: [],
        }

        schema = _build_settings_schema(
            cached_lists=self._cached_lists,
            defaults=defaults,
        )
        return self.async_show_form(step_id="select", data_schema=schema, errors=errors)

    async def async_step_ai_labels_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Setup-time AI Label Mapping (shown only when motion sensors selected)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            person = _dedupe_normalize_label_list(user_input.get(CONF_AI_PERSON_LABELS) or [])
            vehicle = _dedupe_normalize_label_list(user_input.get(CONF_AI_VEHICLE_LABELS) or [])
            animal = _dedupe_normalize_label_list(user_input.get(CONF_AI_ANIMAL_LABELS) or [])

            self._pending_options[CONF_AI_PERSON_LABELS] = person
            self._pending_options[CONF_AI_VEHICLE_LABELS] = vehicle
            self._pending_options[CONF_AI_ANIMAL_LABELS] = animal

            title = DEFAULT_NAME
            return self.async_create_entry(title=title, data=self._data, options=self._pending_options)

        # Prefer pending values if they exist (user went back/forward); otherwise show defaults.
        if CONF_AI_PERSON_LABELS in self._pending_options:
            default_person = self._pending_options.get(CONF_AI_PERSON_LABELS, [])
        else:
            default_person = DEFAULT_PERSON_LABELS
        
        if CONF_AI_VEHICLE_LABELS in self._pending_options:
            default_vehicle = self._pending_options.get(CONF_AI_VEHICLE_LABELS, [])
        else:
            default_vehicle = DEFAULT_VEHICLE_LABELS
        
        if CONF_AI_ANIMAL_LABELS in self._pending_options:
            default_animal = self._pending_options.get(CONF_AI_ANIMAL_LABELS, [])
        else:
            default_animal = DEFAULT_ANIMAL_LABELS

        schema = vol.Schema(
            {
                vol.Optional(CONF_AI_PERSON_LABELS, default=default_person): _ai_label_selector(),
                vol.Optional(CONF_AI_VEHICLE_LABELS, default=default_vehicle): _ai_label_selector(),
                vol.Optional(CONF_AI_ANIMAL_LABELS, default=default_animal): _ai_label_selector(),
            }
        )

        return self.async_show_form(
            step_id="ai_labels_setup",
            data_schema=schema,
            errors=errors,
            description_placeholders={"help": AI_LABELS_HELP},
        )

    async def async_step_import(self, info: dict[str, Any]) -> FlowResult:
        host = str(info.get(CONF_HOST, "")).strip()
        port = int(info.get(CONF_PORT, DEFAULT_PORT))
        ssl = bool(info.get(CONF_SSL, False))

        await self.async_set_unique_id(_unique_id(host, port, ssl))
        self._abort_if_unique_id_configured()

        title = DEFAULT_NAME

        data = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_SSL: ssl,
            CONF_VERIFY_SSL: bool(info.get(CONF_VERIFY_SSL, False)),
            CONF_USERNAME: str(info.get(CONF_USERNAME, "")),
            CONF_PASSWORD: str(info.get(CONF_PASSWORD, "")),
        }
        return self.async_create_entry(title=title, data=data)


class BlueIrisOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Blue Iris (2-step).

    Step 1 (init): General settings (cameras/sensors/etc.)
    Step 2 (ai_labels): AI Label Mapping (only if motion sensors enabled)
    """

    def __init__(self) -> None:
        self._cached_lists: dict[str, list[selector.SelectOptionDict]] = {}
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._pending = dict(user_input)

            allowed_motion = self._pending.get(
                CONF_ALLOWED_MOTION_SENSOR,
                self.config_entry.options.get(CONF_ALLOWED_MOTION_SENSOR, []),
            )

            if allowed_motion:
                return await self.async_step_ai_labels()

            return self.async_create_entry(title="", data=self._pending)

        api = None
        try:
            entry = self.config_entry
            cfg = BlueIrisConfig(
                host=str(entry.data.get(CONF_HOST, "")),
                port=int(entry.data.get(CONF_PORT, DEFAULT_PORT)),
                ssl=bool(entry.data.get(CONF_SSL, False)),
                verify_ssl=bool(entry.data.get(CONF_VERIFY_SSL, False)),
                username=str(entry.data.get(CONF_USERNAME, "")),
                password=str(entry.data.get(CONF_PASSWORD, "")),
                stream_type=str(entry.options.get(CONF_STREAM_TYPE, DEFAULT_STREAM_TYPE)),
            )
            api = BlueIrisApi(self.hass, cfg)
            await api.async_update()

            camera_opts = [selector.SelectOptionDict(value=c.id, label=c.name) for c in api.camera_list]
            camera_opts_filtered = [
                selector.SelectOptionDict(value=c.id, label=c.name)
                for c in api.camera_list
                if not _is_filtered_camera(c)
            ]

            profiles = api.data.get("profiles", []) or []
            profile_opts = [selector.SelectOptionDict(value=str(idx), label=str(name)) for idx, name in enumerate(profiles)]

            schedules = api.data.get("schedules", []) or []
            schedule_opts = [
                selector.SelectOptionDict(value=str(idx), label=str(name)) for idx, name in enumerate(schedules)
            ]

            self._cached_lists = {
                "camera_all": camera_opts,
                "camera_filtered": camera_opts_filtered,
                CONF_ALLOWED_PROFILE: profile_opts,
                CONF_ALLOWED_SCHEDULE: schedule_opts,
            }

        except Exception:
            _LOGGER.debug("Failed to fetch lists for options flow", exc_info=True)
        finally:
            try:
                if api is not None:
                    await api.async_close()
            except Exception:
                pass

        options = self.config_entry.options
        defaults = {
            CONF_LOG_LEVEL: options.get(CONF_LOG_LEVEL, LOG_LEVEL_DEFAULT),
            CONF_STREAM_TYPE: options.get(CONF_STREAM_TYPE, DEFAULT_STREAM_TYPE),
            CONF_SUPPORT_STREAM: bool(options.get(CONF_SUPPORT_STREAM, False)),
            CONF_HOLD_PROFILE_CHANGES: bool(options.get(CONF_HOLD_PROFILE_CHANGES, DEFAULT_HOLD_PROFILE_CHANGES)),
            CONF_ALLOWED_CAMERA: options.get(CONF_ALLOWED_CAMERA, []),
            CONF_ALLOWED_PROFILE: options.get(CONF_ALLOWED_PROFILE, []),
            CONF_ALLOWED_SCHEDULE: options.get(CONF_ALLOWED_SCHEDULE, []),
            CONF_ALLOWED_MOTION_SENSOR: options.get(CONF_ALLOWED_MOTION_SENSOR, []),
            CONF_ALLOWED_AUDIO_SENSOR: options.get(CONF_ALLOWED_AUDIO_SENSOR, []),
            CONF_ALLOWED_CONNECTIVITY_SENSOR: options.get(CONF_ALLOWED_CONNECTIVITY_SENSOR, []),
            CONF_ALLOWED_DIO_SENSOR: options.get(CONF_ALLOWED_DIO_SENSOR, []),
            CONF_ALLOWED_EXTERNAL_SENSOR: options.get(CONF_ALLOWED_EXTERNAL_SENSOR, []),
        }

        schema = _build_settings_schema(
            cached_lists=self._cached_lists,
            defaults=defaults,
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_ai_labels(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """AI Label Mapping options (shown only when motion sensors enabled)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            person = _dedupe_normalize_label_list(user_input.get(CONF_AI_PERSON_LABELS) or [])
            vehicle = _dedupe_normalize_label_list(user_input.get(CONF_AI_VEHICLE_LABELS) or [])
            animal = _dedupe_normalize_label_list(user_input.get(CONF_AI_ANIMAL_LABELS) or [])

            self._pending[CONF_AI_PERSON_LABELS] = person
            self._pending[CONF_AI_VEHICLE_LABELS] = vehicle
            self._pending[CONF_AI_ANIMAL_LABELS] = animal

            return self.async_create_entry(title="", data=self._pending)

        opts = self.config_entry.options

        # Prefer in-memory pending values (user went back/forward), then saved options,
        # and only then fall back to defaults.
        if CONF_AI_PERSON_LABELS in self._pending:
            default_person = self._pending.get(CONF_AI_PERSON_LABELS, [])
        elif CONF_AI_PERSON_LABELS in opts:
            default_person = opts.get(CONF_AI_PERSON_LABELS, [])
        else:
            default_person = DEFAULT_PERSON_LABELS
        
        if CONF_AI_VEHICLE_LABELS in self._pending:
            default_vehicle = self._pending.get(CONF_AI_VEHICLE_LABELS, [])
        elif CONF_AI_VEHICLE_LABELS in opts:
            default_vehicle = opts.get(CONF_AI_VEHICLE_LABELS, [])
        else:
            default_vehicle = DEFAULT_VEHICLE_LABELS
        
        if CONF_AI_ANIMAL_LABELS in self._pending:
            default_animal = self._pending.get(CONF_AI_ANIMAL_LABELS, [])
        elif CONF_AI_ANIMAL_LABELS in opts:
            default_animal = opts.get(CONF_AI_ANIMAL_LABELS, [])
        else:
            default_animal = DEFAULT_ANIMAL_LABELS

        schema = vol.Schema(
            {
                vol.Optional(CONF_AI_PERSON_LABELS, default=default_person): _ai_label_selector(),
                vol.Optional(CONF_AI_VEHICLE_LABELS, default=default_vehicle): _ai_label_selector(),
                vol.Optional(CONF_AI_ANIMAL_LABELS, default=default_animal): _ai_label_selector(),
            }
        )

        return self.async_show_form(
            step_id="ai_labels",
            data_schema=schema,
            errors=errors,
            description_placeholders={"help": AI_LABELS_HELP},
        )