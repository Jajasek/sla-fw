# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import shutil
import tarfile
import tempfile
from typing import Optional, Any, Dict
from urllib.request import urlopen, Request

import distro
import pydbus
from PySignal import Signal

from sl1fw import defines
from sl1fw.project.functions import ramdisk_cleanup


class Network:
    NETWORKMANAGER_SERVICE = "org.freedesktop.NetworkManager"
    HOSTNAME_SERVICE = "org.freedesktop.hostname1"
    NM_STATE_CONNECTED_GLOBAL = 70

    def __init__(self, cpu_serial_no):
        self.logger = logging.getLogger(__name__)
        self.version_id = distro.version()
        self.cpu_serial_no = cpu_serial_no
        self.assign_active = None
        self.net_change = Signal()
        self.bus = pydbus.SystemBus()
        self.nm = self.bus.get(self.NETWORKMANAGER_SERVICE)
        self.hostname_service = self.bus.get(self.HOSTNAME_SERVICE)

    def register_events(self) -> None:
        """
        Start network monitoring
        Use net_change signal to register for network state updates

        :return: None
        """
        self.nm.PropertiesChanged.connect(self._state_changed)
        for device_path in self.nm.GetAllDevices():
            device = self.bus.get(self.NETWORKMANAGER_SERVICE, device_path)
            device.PropertiesChanged.connect(self._state_changed)

    def force_refresh_state(self):
        self.net_change.emit(self.online)

    @property
    def online(self) -> bool:
        return self.nm.state() == self.NM_STATE_CONNECTED_GLOBAL

    def _state_changed(self, changed: map) -> None:
        events = {'Connectivity', 'Metered', 'ActiveConnections', 'WirelessEnabled'}
        if not events & set(changed.keys()):
            return

        self.force_refresh_state()
        self.logger.debug("NetworkManager state changed: %s, devices: %s", changed, self.devices)

    @property
    def ip(self) -> Optional[str]:
        connection_path = self.nm.PrimaryConnection

        if connection_path == "/":
            return None

        return self._get_ipv4(self._get_nm_obj(connection_path).Ip4Config)

    @property
    def devices(self) -> Dict[str, str]:
        """
        Get network device dictionary

        :return: {interface_name: ip_address}
        """
        return {dev.Interface: self._get_ipv4(dev.Ip4Config) for dev in
                [self._get_nm_obj(dev_path) for dev_path in self.nm.GetAllDevices()] if
                dev.Interface != "lo" and dev.Ip4Config != "/"}

    @property
    def hostname(self) -> str:
        return self.hostname_service.StaticHostname

    @hostname.setter
    def hostname(self, hostname: str) -> None:
        self.hostname_service.SetStaticHostname(hostname, False)
        self.hostname_service.SetHostname(hostname, False)

    def _get_ipv4(self, ipv4_config_path: str) -> Optional[str]:
        """
        Resolves IPv4 address string from NetworkManager ipv4 configuration object path

        :param ipv4_config_path: D-Bus path to NetworkManager ipv4 configuration
        :return: IP address as string or None
        """
        if ipv4_config_path == "/":
            return None

        ipv4 = self._get_nm_obj(ipv4_config_path)

        if not ipv4.AddressData:
            return None

        return ipv4.AddressData[0]['address']

    def _get_nm_obj(self, path: str) -> Any:
        """
        Get NetworkManager D-Bus object by path
        :param path:
        :return:
        """
        return self.bus.get(self.NETWORKMANAGER_SERVICE, path)

    def download_url(self, url: str, dest: str, page=None, timeout_sec=10) -> None:
        """
        Fetches file specified by url info destination while displaying progress

        This is implemented as chunked copy from source file descriptor to the destination file descriptor. The progress
        is updated once the chunk is copied. The source file descriptor is either standard file when the source is
        mounted USB drive or urlopen result.

        :param url: Source url
        :param dest: Destination file
        :param page: Wait page to update
        :param timeout_sec: Timeout in seconds
        :return: None
        """

        if page:
            page.showItems(line2="0%")

        self.logger.info("Downloading %s" % url)

        if url.startswith("http://") or url.startswith("https://"):
            # URL is HTTP, source is url
            req = Request(url)
            req.add_header('User-Agent', 'Prusa-SL1')
            req.add_header('Prusa-SL1-version', self.version_id)
            req.add_header('Prusa-SL1-serial', self.cpu_serial_no)
            source = urlopen(req, timeout=timeout_sec)

            # Default files size (sometimes HTTP server does not know size)
            content_length = source.info().get("Content-Length")
            if content_length is not None:
                file_size = int(content_length)
            else:
                file_size = None

            block_size = 8 * 1024
        else:
            # URL is file, source is file
            self.logger.info("Copying file %s" % url)
            source = open(url, "rb")
            file_size = os.path.getsize(url)
            block_size = 1024 * 1024

        with open(dest, 'wb') as file:
            old_progress = 0
            while True:
                buffer = source.read(block_size)
                if not buffer or buffer == '':
                    break
                file.write(buffer)

                if file_size is not None:
                    progress = int(100 * file.tell() / file_size)
                else:
                    progress = 0

                if page and progress != old_progress:
                    page.showItems(line2="%d%%" % progress)
                    old_progress = progress

            if file_size and file.tell() != file_size:
                raise Exception("Download of %s failed to read whole file %d != %d", url, file_size, file.tell())

        source.close()

    def download_examples(self, page) -> None:
        # remove old projects from ramdisk, downloader uses another ramdisk but this *may* help in some cases
        ramdisk_cleanup(self.logger)
        failed = "."
        try:
            if not self.ip:
                failed = _(": Not connected to network!")
                raise Exception("Not connected to network")

            statvfs = os.statvfs(defines.internalProjectPath)
            internalAvailable = statvfs.f_frsize * statvfs.f_bavail - defines.internalReservedSpace
            self.logger.debug("Internal storage available space: %d bytes" % internalAvailable)
            # if internal storage is full, quit immediately
            if internalAvailable < 0:
                failed = _(": Not enough free space in the internal storage!")
                raise Exception("Not enough free space in the internal storage")

            if not os.path.isdir(defines.internalProjectPath):
                os.makedirs(defines.internalProjectPath)

            with tempfile.NamedTemporaryFile() as archive:
                page.showItems(line1 = _("Fetching examples"))
                self.download_url(defines.examplesURL, archive.name, page)
                page.showItems(line1 = _("Extracting examples"), line2="")

                with tempfile.TemporaryDirectory() as temp:
                    extractedSize = 0
                    with tarfile.open(fileobj=archive) as tar:
                        for member in tar.getmembers():
                            self.logger.debug("Found '%s' (%d bytes)", member.name, member.size)
                            extractedSize += member.size
                            tar.extract(member, temp)

                    if extractedSize > internalAvailable:
                        failed = _(": Not enough free space in the internal storage!")
                        raise Exception("Not enough free space in the internal storage")

                    page.showItems(line1 = _("Storing examples"))
                    for item in os.listdir(temp):
                        dest = os.path.join(defines.internalProjectPath, item)
                        if os.path.exists(dest):
                            shutil.rmtree(dest)
                        shutil.copytree(os.path.join(temp, item), dest)

                    page.showItems(line1 = _("Cleaning up"))

        except Exception as e:
            self.logger.exception("Examples download failed: " + str(e))
            raise Exception(failed)
