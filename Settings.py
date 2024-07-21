class Settings:
    relays = {}
    inputs = {}
    ip = ""
    subnet_mask = ""
    gateway = ""
    dns_server = ""
    mqtt_broker = "your_mqtt_broker_ip"
    mqtt_topic_prefix = "pico/relay"

    @classmethod
    def load_settings(cls):
        import sys
        if 'config' in sys.modules:
            del sys.modules['config']
        import config
        cls.relays = config.relays
        cls.inputs = config.inputs
        cls.ip = getattr(config, 'ip', cls.ip)
        cls.subnet_mask = getattr(config, 'subnet_mask', cls.subnet_mask)
        cls.gateway = getattr(config, 'gateway', cls.gateway)
        cls.dns_server = getattr(config, 'dns_server', cls.dns_server)
        cls.mqtt_broker = getattr(config, 'mqtt_broker', cls.mqtt_broker)
        cls.mqtt_topic_prefix = getattr(config, 'mqtt_topic_prefix', cls.mqtt_topic_prefix)

    @classmethod
    def save_settings(cls):
        settings_str = f"""relays = {cls.relays}
inputs = {cls.inputs}
ip = "{cls.ip}"
subnet_mask = "{cls.subnet_mask}"
gateway = "{cls.gateway}"
dns_server = "{cls.dns_server}"
mqtt_broker = "{cls.mqtt_broker}"
mqtt_topic_prefix = "{cls.mqtt_topic_prefix}"
"""
        with open("config.py", "w") as fp:
            fp.write(settings_str)

    @classmethod
    def initialize(cls):
        cls.load_settings()

# Initialize settings when the module is imported
Settings.initialize()
