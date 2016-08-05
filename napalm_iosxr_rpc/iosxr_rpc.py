# -*- coding: utf-8 -*-
# Copyright 2016 CloudFlare, Inc. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""
NAPALM IOS-XR RPC Driver module.
"""

# python std lib
import re

# third party libs
from lxml import etree
from iosxr_eznc.device import Device as NcDevice
# from iosxr_grpc.device import Device as gRPCDevice
from iosxr_eznc.exception import ConnectError as XRConnectError
from iosxr_eznc.exception import ConnectError as XRConnectAuthError
from iosxr_eznc.exception import ConnectUnknownHostError as XRConnectUnknownHostError
from iosxr_eznc.exception import ConnectionClosedError as XRConnectionClosedError
from iosxr_eznc.exception import RPCError as XRRPCError
from iosxr_eznc.exception import RPCTimeoutError as XRRPCTimeoutError
from iosxr_eznc.exception import GetConfigurationError as XRGetConfigurationError
from iosxr_eznc.exception import LockError as XRLockError
from iosxr_eznc.exception import UnlockError as XRUnlockError
from iosxr_eznc.exception import DiscardChangesError as XRDiscardChangesError

# !! all exception imports wil be converted to:
# from iosxr_base.exception import ConnectError as XRConnectError
# from iosxr_base.exception import ConnectError as XRConnectAuthError
# from iosxr_base.exception import ConnectUnknownHostError as XRConnectUnknownHostError
# from iosxr_base.exception import ConnectionClosedError as XRConnectionClosedError
# from iosxr_base.exception import RPCError as XRRPCError
# from iosxr_base.exception import RPCTimeoutError as XRRPCTimeoutError
# from iosxr_base.exception import GetConfigurationError as XRGetConfigurationError
# from iosxr_base.exception import LockError as XRLockError
# from iosxr_base.exception import UnlockError as XRUnlockError
# from iosxr_base.exception import DiscardChangesError as XRDiscardChangesError
# !! only when iosxr_base and iosxr_grpc are ready

# ~~~ NAPALM base ~~~
# base network driver class
from napalm_base.base import NetworkDriver
# helpers
from napalm_base.helpers import ip as IP
from napalm_base.helpers import mac as MAC
from napalm_base.helpers import convert
from napalm_base.helpers import find_txt
# exceptions
from napalm_base.exceptions import ConnectionException as NapalmConnectionException
from napalm_base.exceptions import MergeConfigException as NapalmMergeConfigException
from napalm_base.exceptions import CommandErrorException as NapalmCommandErrorException
from napalm_base.exceptions import SessionLockedException as NapalmSessionLockedException
from napalm_base.exceptions import ReplaceConfigException as NapalmReplaceConfigException
from napalm_base.exceptions import CommandTimeoutException as NapalmCommandTimeoutException


class IOSXRRPCDriver(NetworkDriver):

    """
    IOS-XR RPC driver class.
    """

    DEFAULT_NC_PORT = 830
    DEFAULT_GRPC_PORT = 57400

    def __init__(self,
                 hostname,
                 username,
                 password,
                 timeout=60,
                 optional_args=None):

        self._hostname = hostname
        self._username = username
        self._password = password
        self._timeout = timeout

        if optional_args is None:
            optional_args = {}
        self.__netconf = optional_args.get('iosxr_transport', '').lower() != 'grpc'
        # for anything else than `grpc`, will try to establish a NETCONF-YANG communication channel
        self._default_port = self.DEFAULT_NC_PORT if self.__netconf else self.DEFAULT_GRPC_PORT
        self._port = optional_args.get('port', self._default_port)
        self._config_lock = optional_args.get('config_lock', True)
        # default lock behavior is True
        # see for further explanation: https://github.com/napalm-automation/napalm-ios/issues/21
        # will be changed to False, together with JunOS, IOS-XR and perhaps IOS/IOS-XE too

        __device_class = NcDevice
        # when iosxr_grpc is born
        # if self.__netconf is False:
        #     __device_class = gRPCDevice

        self._locked = False
        self._connected = False
        self._dev = __device_class(self._hostname,
                                   user=self._username,
                                   password=self._password,
                                   port=self._port,
                                   timeout=self._timeout)

    def _lock(self):

        """
        Lockes the configuration DB.

        :raises napalm_base.exceptions.SessionLockedException: cannot lock the config DB.
        """

        if not self._locked:
            try:
                self._dev.rpc.lock()
                self._locked = True
            except XRLockError as lock_err:
                raise NapalmSessionLockedException(lock_err.message)

    def _unlock(self):

        """
        Unlocks the configuration DB.

        :raises napalm_base.exceptions.SessionLockedException: unable to unlock.
        """

        if self._locked:
            try:
                self._dev.rpc.unlock()
                self._locked = False
            except XRUnlockError as unlock_err:
                raise NapalmSessionLockedException(unlock_err.message)

    def open(self):

        """
        Opens the connection with the network device.

        :raises napalm_base.exceptions.ConnectionException: unable to open the SSH connection.
        """

        try:
            self._dev.open()
        except (XRConnectError, XRConnectAuthError, XRConnectUnknownHostError, XRConnectionClosedError) as cerr:
            raise NapalmConnectionException(cerr.message)

        if self._config_lock:
            self._lock()

    def close(self):
        if self._config_lock:
            self._unlock()
        self._dev.close()
