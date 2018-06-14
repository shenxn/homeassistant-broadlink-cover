"""
 Copyright 2017 SHENXN
 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.

 Modified from https://github.com/home-assistant/home-assistant/blob/dev/homeassistant/components/switch/broadlink.py
"""
from datetime import timedelta
from base64 import b64encode, b64decode
import asyncio
import binascii
import logging
import socket

import voluptuous as vol

from homeassistant.util.dt import utcnow
from homeassistant.util import Throttle
from homeassistant.components.cover import (CoverDevice, PLATFORM_SCHEMA, SUPPORT_OPEN, SUPPORT_CLOSE, SUPPORT_STOP)
from homeassistant.const import (
    CONF_FRIENDLY_NAME, CONF_COMMAND_OPEN,
    CONF_COMMAND_CLOSE, CONF_COMMAND_STOP,
    CONF_COVERS, CONF_TIMEOUT,
    CONF_HOST, CONF_MAC)
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['broadlink==0.9.0']

_LOGGER = logging.getLogger(__name__)

TIME_BETWEEN_UPDATES = timedelta(seconds=5)

DOMAIN = 'broadlink'
DEFAULT_NAME = 'Broadlink cover'
DEFAULT_TIMEOUT = 10
DEFAULT_RETRY = 3

COVER_SCHEMA = vol.Schema({
    vol.Optional(CONF_COMMAND_OPEN, default=None): cv.string,
    vol.Optional(CONF_COMMAND_CLOSE, default=None): cv.string,
    vol.Optional(CONF_COMMAND_STOP, default=None): cv.string,
    vol.Optional(CONF_FRIENDLY_NAME): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_COVERS, default={}):
        vol.Schema({cv.slug: COVER_SCHEMA}),
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up Broadlink covers."""
    import broadlink
    devices = config.get(CONF_COVERS)
    ip_addr = config.get(CONF_HOST)
    friendly_name = config.get(CONF_FRIENDLY_NAME)
    mac_addr = binascii.unhexlify(
        config.get(CONF_MAC).encode().replace(b':', b''))

    broadlink_device = broadlink.rm((ip_addr, 80), mac_addr, None)

    covers = []
    for object_id, device_config in devices.items():
        covers.append(
            BroadlinkRMCover(
                device_config.get(CONF_FRIENDLY_NAME, object_id),
                broadlink_device,
                device_config.get(CONF_COMMAND_OPEN),
                device_config.get(CONF_COMMAND_CLOSE),
                device_config.get(CONF_COMMAND_STOP)
            )
        )

    broadlink_device.timeout = config.get(CONF_TIMEOUT)
    try:
        broadlink_device.auth()
    except socket.timeout:
        _LOGGER.error("Failed to connect to device")

    add_devices(covers)


class BroadlinkRMCover(CoverDevice):
    """Representation of an Broadlink cover."""

    def __init__(self, friendly_name, device, command_open, command_close, command_stop):
        """Initialize the cover."""
        self._name = friendly_name
        self._state = False
        self._command_open = b64decode(command_open) if command_open else None
        self._command_close = b64decode(command_close) if command_close else None
        self._command_stop = b64decode(command_stop) if command_stop else None
        self._device = device

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return True

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def is_closed(self):
        """Return true if device is closed."""
        return self._state
    
    @property
    def supported_features(self):
      support_features = 0
      if self._command_open is not None:
        support_features |= SUPPORT_OPEN
      if self._command_close is not None:
        support_features |= SUPPORT_CLOSE
      if self._command_stop is not None:
        support_features |= SUPPORT_STOP
      return support_features

    def open_cover(self, **kwargs):
        """Open the cover."""
        self._sendpacket(self._command_open)

    def close_cover(self, **kwargs):
        """Close the cover."""
        self._sendpacket(self._command_close)

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        self._sendpacket(self._command_stop)

    def _sendpacket(self, packet, retry=2):
        """Send packet to device."""
        if packet is None:
            _LOGGER.debug("Empty packet")
            return True
        try:
            self._device.send_data(packet)
        except (socket.timeout, ValueError) as error:
            if retry < 1:
                _LOGGER.error(error)
                return False
            if not self._auth():
                return False
            return self._sendpacket(packet, retry-1)
        return True

    def _auth(self, retry=2):
        try:
            auth = self._device.auth()
        except socket.timeout:
            auth = False
        if not auth and retry > 0:
            return self._auth(retry-1)
        return auth
