import uasyncio
import network
from machine import Pin, Timer
import socket
from NetworkCredentials import NetworkCredentials
from Settings import Settings

class WifiConnection:
    def __init__(self, dn33c08=None):
        self.dn33c08 = dn33c08
        self.wlan = network.WLAN(network.STA_IF)
        self.status = network.STAT_IDLE
        self.connection_timer = Timer(-1)
        if self.dn33c08:
            self.dn33c08.register_button_callback(3, self.display_ip_from_settings)
            self.dn33c08.register_button_callback(4, self.display_ip)

    def start_and_maintain_connection(self, check_interval_ms=30000):
        self.connection_timer.init(period=check_interval_ms, mode=Timer.PERIODIC, callback=self._check_connection)

    def _check_connection(self, timer):
        if not self.wlan.isconnected():
            print("WiFi disconnected. Attempting to reconnect...")
            uasyncio.create_task(self._reconnect())
        else:
            print("WiFi is connected. IP:", self.wlan.ifconfig())

    async def _reconnect(self):
        connected = await self.connect()
        if not connected:
            print("Reconnection failed")
            if self.dn33c08:
                self.dn33c08.blink_led(4)

    def display_ip_from_settings(self, button=2):
        self.display_ip(Settings.ip, button*600)

    def display_actual_ip(self, button=2):
        self.display_ip(0, button*500)

    def display_ip(self, ip, duration=2000):
        if self.dn33c08 is None:
            print("DN33C08 instance not set, cannot display IP")
            return
        if not(isinstance(ip, str)):
            ip=self.wlan.ifconfig()[0]
            print(ip)
        ip_parts = ip.split('.')
        third_octet_last_digit = ip_parts[-2][-1]
        last_octet = ip_parts[-1]
        display_value = f"{third_octet_last_digit}{int(last_octet):3d}"
        print(f"Displaying IP: {display_value}")
        self.dn33c08.set_display(display_value, ".   ", duration)

    async def connect(self):
        print(f"Connecting to Wi-Fi - please wait")
        self.wlan.active(False)
        await uasyncio.sleep_ms(300)
        self.wlan.active(True)
        self.wlan.connect(NetworkCredentials.ssid, NetworkCredentials.password)
        await self.wait_for_connection()
        print(f"Status after wait_for_connection: {self.status}")
        if self.status == network.STAT_GOT_IP:
            print("Attempting to set static IP")
            if await self.try_static_ip(Settings.ip):
                return True
            
            print("Static IP configuration failed. Falling back to DHCP.")
            self.wlan.ifconfig('dhcp')
            await uasyncio.sleep(5)  # Wait for DHCP to assign an IP
            print(f"Connected with DHCP. IP: {self.wlan.ifconfig()[0]}")
            return True
        else:
            print(f"Connection failed with status: {self.status}")
            self.display_actual_ip()
        return False

    async def ping_test(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect(("8.8.8.8", 53))
            s.close()
            return True
        except:
            return False

    async def try_static_ip(self, ip):
        print(f"Trying static IP: {ip}")
        self.wlan.ifconfig((ip, Settings.subnet_mask, Settings.gateway, Settings.dns_server))
        await uasyncio.sleep(2)  # Wait for settings to apply
        if await self.ping_test():
            print(f"Connected successfully with IP: {ip}")
            return True
        return False

    async def wait_for_connection(self):
        max_wait = 20
        while max_wait > 0:
            self.status = self.wlan.status()
            print(f"Current status: {self.status}")
            if self.status < 0 or self.status >= 3:
                break
            max_wait -= 1
            await uasyncio.sleep(1)
        print(f"Final status after waiting: {self.status}")
