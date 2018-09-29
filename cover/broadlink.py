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
import logging
import time
import voluptuous as vol
import broadlink
import binascii
import socket
from base64 import b64encode, b64decode

from homeassistant.components.cover import (
    CoverDevice, ENTITY_ID_FORMAT, PLATFORM_SCHEMA, SUPPORT_OPEN, SUPPORT_CLOSE, SUPPORT_STOP)
from homeassistant.const import (
    CONF_IP_ADDRESS, CONF_MAC, CONF_COVERS, CONF_DEVICE, CONF_COMMAND_OPEN, CONF_COMMAND_CLOSE, CONF_COMMAND_STOP, CONF_TRIGGER_TIME, CONF_TIMEOUT, CONF_FRIENDLY_NAME, STATE_CLOSED, STATE_OPEN, STATE_UNKNOWN)
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['broadlink==0.9.0']

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'broadlink'

STATE_CLOSING = 'closing'
STATE_OFFLINE = 'offline'
STATE_OPENING = 'opening'
STATE_STOPPED = 'stopped'

DEFAULT_TIMEOUT = 10
DEFAULT_RETRY = 3

COVER_SCHEMA = vol.Schema({
    vol.Optional(CONF_COMMAND_OPEN, default=None): cv.string,
    vol.Optional(CONF_COMMAND_CLOSE, default=None): cv.string,
    vol.Optional(CONF_COMMAND_STOP, default=None): cv.string,
    vol.Optional(CONF_TRIGGER_TIME, default=DEFAULT_TIMEOUT): cv.positive_int,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    vol.Optional(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_IP_ADDRESS): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_COVERS): vol.Schema({cv.slug: COVER_SCHEMA}),
    vol.Optional(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the broadlink covers."""
    covers = []
    devices = config.get(CONF_COVERS)
    ip_addr = config.get(CONF_IP_ADDRESS)
    mac_addr = config.get(CONF_MAC)

    for object_id, device_config in devices.items():
        
        mac_addr = binascii.unhexlify(
            mac_addr.encode().replace(b':', b''))
        broadlink_device = broadlink.rm((ip_addr, 80), mac_addr, None)
        
        args = {
            CONF_COMMAND_OPEN: device_config.get(CONF_COMMAND_OPEN),
            CONF_COMMAND_CLOSE: device_config.get(CONF_COMMAND_CLOSE),
            CONF_COMMAND_STOP: device_config.get(CONF_COMMAND_STOP),
            CONF_TRIGGER_TIME: device_config.get(CONF_TRIGGER_TIME),
            CONF_FRIENDLY_NAME: device_config.get(CONF_FRIENDLY_NAME, object_id),
            CONF_DEVICE: broadlink_device
        }
        
        covers.append(BroadlinkRMCover(hass, args, object_id))

    broadlink_device.timeout = config.get(CONF_TIMEOUT)
    try:
        broadlink_device.auth()
    except socket.timeout:
        _LOGGER.error("Failed to connect to device")

    add_devices(covers, True)

class BroadlinkRMCover(CoverDevice):
    """Representation of Broadlink cover."""

    # pylint: disable=no-self-use
    def __init__(self, hass, args, object_id):
        """Initialize the cover."""
        self.hass = hass
        self.entity_id = ENTITY_ID_FORMAT.format(object_id)
        self._name = args[CONF_FRIENDLY_NAME]
        self._device = args[CONF_DEVICE]
        self._available = True
        self._state = None
        self._command_open = b64decode(args[CONF_COMMAND_OPEN]) if args[CONF_COMMAND_OPEN] else None
        self._command_close = b64decode(args[CONF_COMMAND_CLOSE]) if args[CONF_COMMAND_CLOSE] else None
        self._command_stop = b64decode(args[CONF_COMMAND_STOP]) if args[CONF_COMMAND_STOP] else None
        self._trigger_time = args[CONF_TRIGGER_TIME]

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        if self._state in [STATE_UNKNOWN, STATE_OFFLINE]:
            return None
        return self._state in [STATE_CLOSED, STATE_OPENING]

    @property
    def close_cover(self):
        """Close the cover."""
        self._sendpacket(self._command_close)
        time.sleep(self._trigger_time)
        self._sendpacket(self._command_stop)
        self._state = STATE_CLOSED

    def open_cover(self):
        """Open the cover."""
        self._sendpacket(self._command_open)
        self._state = STATE_OPEN

    def stop_cover(self):
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
        
    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return 'garage'

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP