import uasyncio
import network
from machine import Pin
import socket
from NetworkCredentials import NetworkCredentials
from Settings import Settings

class WifiConnection:
    status = network.STAT_IDLE
    wlan = None
    led = Pin("LED", Pin.OUT)
    dn33c08 = None

    @classmethod
    def set_dn33c08(cls, dn33c08_instance):
        cls.dn33c08 = dn33c08_instance
        print("DN33C08 instance set")

    @classmethod
    async def start_and_maintain_connection(cls, check_interval_ms=30000):
        cls.wlan = network.WLAN(network.STA_IF)
        cls.wlan.active(True)
        
        while True:
            if not cls.wlan.isconnected():
                print("WiFi disconnected. Attempting to reconnect...")
                connected = await cls.connect()
                if connected:
                    print("Reconnection successful")
                    uasyncio.create_task(cls.blink_network_connected())
                    uasyncio.create_task(cls.start_display_ip_success())
                else:
                    print("Reconnection failed")
                    uasyncio.create_task(cls.blink_no_network())
                    uasyncio.create_task(cls.display_ip_failed())
            else:
                print("WiFi is connected. IP:", cls.wlan.ifconfig())
                uasyncio.create_task(cls.blink_network_connected())
                uasyncio.create_task(cls.start_display_ip_success())
            
            for _ in range(60):  # Check every 500ms for 30 seconds
                await uasyncio.sleep_ms(500)
                if not cls.wlan.isconnected():
                    print("WiFi connection lost")
                    break

    @classmethod
    async def display_ip_failed(cls):
        if cls.dn33c08 is None:
            print("DN33C08 instance not set, cannot display IP")
            return
        ip_parts = Settings.ip.split('.')
        while not cls.wlan.isconnected():
            try:
                third_octet_last_digit = ip_parts[-2][-1]
                last_octet = ip_parts[-1]
                display_value = f"{third_octet_last_digit}{int(last_octet):3d}"
                print(f"Displaying failed IP: {display_value}")
                cls.dn33c08.set_display(display_value, ".   ", 2000)
            except Exception as e:
                print(f"Error displaying failed IP: {e}")
            await uasyncio.sleep(1)

    @classmethod
    async def display_ip_success(cls):
        if cls.dn33c08 is None:
            print("DN33C08 instance not set, cannot display IP")
            return
        while cls.wlan.isconnected():
            try:
                if cls.dn33c08.buttons[3].value() == 0:  # Button 4 pressed
                    ip_parts = cls.wlan.ifconfig()[0].split('.')
                    third_octet_last_digit = ip_parts[-2][-1]
                    last_octet = ip_parts[-1]
                    display_value = f"{third_octet_last_digit}{int(last_octet):3d}"
                    print(f"Displaying success IP: {display_value}")
                    cls.dn33c08.set_display(display_value, ".   ", 2000)
            except Exception as e:
                print(f"Error displaying success IP: {e}")
            await uasyncio.sleep_ms(100)  # Check button press every 100ms

    @classmethod
    async def connect(cls):
        print(f"Connecting to Wi-Fi - please wait")
        cls.wlan.connect(NetworkCredentials.ssid, NetworkCredentials.password)
        await cls.wait_for_connection()
        print(f"Status after wait_for_connection: {cls.status}")
        if cls.status == network.STAT_GOT_IP:
            print("Attempting to set static IP")
            if await cls.try_static_ip(Settings.ip):
                return True
            
            print("Static IP configuration failed. Falling back to DHCP.")
            cls.wlan.ifconfig('dhcp')
            await uasyncio.sleep(5)  # Wait for DHCP to assign an IP
            print(f"Connected with DHCP. IP: {cls.wlan.ifconfig()[0]}")
            return True
        else:
            print(f"Connection failed with status: {cls.status}")
        return False

    @classmethod
    async def ping_test(cls):
        try:
            # Try to create a socket and connect to a known IP (e.g., Google's DNS)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect(("8.8.8.8", 53))
            s.close()
            return True
        except:
            return False

    @classmethod
    async def try_static_ip(cls, ip):
        print(f"Trying static IP: {ip}")
        cls.wlan.ifconfig((ip, Settings.subnet_mask, Settings.gateway, Settings.dns_server))
        await uasyncio.sleep(2)  # Wait for settings to apply
        if await cls.ping_test():
            print(f"Connected successfully with IP: {ip}")
            return True
        return False

    @classmethod
    async def wait_for_connection(cls):
        max_wait = 20
        while max_wait > 0:
            cls.status = cls.wlan.status()
            print(f"Current status: {cls.status}")
            if cls.status < 0 or cls.status >= 3:
                break
            max_wait -= 1
            await uasyncio.sleep(1)
        print(f"Final status after waiting: {cls.status}")

    @classmethod
    async def blink_no_network(cls):
        while not cls.wlan.isconnected():
            cls.led.on()
            await uasyncio.sleep_ms(500)
            cls.led.off()
            await uasyncio.sleep_ms(500)

    @classmethod
    async def blink_network_connected(cls):
        while cls.wlan.isconnected():
            cls.led.on()
            await uasyncio.sleep_ms(100)
            cls.led.off()
            await uasyncio.sleep_ms(2900)

    @classmethod
    async def start_display_ip_success(cls):
        print("Starting display IP success task")
        uasyncio.create_task(cls.display_ip_success())
