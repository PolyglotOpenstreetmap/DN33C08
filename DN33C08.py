import uasyncio
import time
from machine import Pin
from Settings import Settings
from LED_8SEG import LED_8SEG
import ujson
from collections import deque

class SimpleQueue:
    def __init__(self, maxsize=20):
        self.queue = deque((), maxsize)
        self._event = uasyncio.Event()

    async def put(self, item):
        self.queue.append(item)
        self._event.set()

    async def get(self):
        while not self.queue:
            self._event.clear()
            await self._event.wait()
        return self.queue.popleft()

class DN33C08:
    def __init__(self):
        self.debounce = 300
        self.update_settings()
        self.last_press_time = {}
        self.last_release_time = {}
        self.input_queue = SimpleQueue(20)
        self.inputs = self._init_inputs()
        self.led_external = Pin(25, Pin.OUT)
        self.relays = self._init_relays()
        self.buttons = self._init_buttons()
        self.led_display = LED_8SEG()
        self.display_buffer = [0] * 4
        self.display_task = None
        self.timers = {}
        self.input_output_mappings = {}
        self._setup_mappings()
        self.button_callbacks = {i: [] for i in range(4)}

    def update_settings(self):
        Settings.load_settings()
        self.relay_config = Settings.relays
        self.input_config = Settings.inputs
        print(Settings.inputs)
        print(Settings.relays)

    def _init_relays(self):
        relay_pins = [13, 12, 28, 27, 26, 19, 17, 16]
        return {i+1: Pin(pin, Pin.OUT) for i, pin in enumerate(relay_pins)}

    def _init_inputs(self):
        input_pins = [3, 4, 5, 6, 7, 8, 14, 15]
        inputs = {}
        for i, pin in enumerate(input_pins):
            input_id = i + 1
            input_pin = Pin(pin, Pin.IN, Pin.PULL_UP)
            input_pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=lambda p, id=input_id: self.handle_interrupt(p, id))
            inputs[input_id] = input_pin
            self.last_press_time[input_id] = 0
            self.last_release_time[input_id] = 0        
        return inputs

    def handle_interrupt(self, pin, input_id):
        if pin.value() == 0:  # Falling edge (button pressed)
            self.handle_pressed_interrupt(pin, input_id)
        else:  # Rising edge (button released)
            self.handle_released_interrupt(pin, input_id)

    def handle_pressed_interrupt(self, pin, input_id):
        current_time = time.ticks_ms()
        if (current_time - self.last_press_time[input_id]) > self.debounce:
            self.last_press_time[input_id] = current_time
            uasyncio.create_task(self.input_queue.put(('activate', input_id)))

    def handle_released_interrupt(self, pin, input_id):
        current_time = time.ticks_ms()
        if (current_time - self.last_release_time[input_id]) > self.debounce:
            self.last_release_time[input_id] = current_time
            uasyncio.create_task(self.input_queue.put(('deactivate', input_id)))

    async def process_input_queue(self):
        while True:
            action, input_id = await self.input_queue.get()
            if action == 'activate':
                await self.handle_input_activation(input_id)
            elif action == 'deactivate':
                await self.handle_input_deactivation(input_id)

    async def handle_input_activation(self, input_id):
        if input_id in self.input_output_mappings:
            mapping = self.input_output_mappings[input_id]
            output_id = mapping['output']
            behavior = mapping['behavior']

            if behavior == 'Toggle':
                self.switch_relay(output_id, 0, mapping['timer_task'])
            elif behavior == 'Timed':
                if not mapping['active']:
                    self.switch_relay(output_id, mapping['duration'], mapping['timer_task'])
                    mapping['active'] = True
                else:
                    self.relays[output_id].value(0)
                    if mapping['timer_task']:
                        mapping['timer_task'].cancel()
                    mapping['active'] = False
            elif behavior == 'Timer_resets':
                if mapping['timer_task']:
                    mapping['timer_task'].cancel()
                mapping['timer_task'] = uasyncio.create_task(self.run_timer(output_id, mapping['duration']))
                self.relays[output_id].value(1)
                mapping['active'] = True
            else:
                self.relays[output_id].value(1)
                mapping['active'] = True

    async def handle_input_deactivation(self, input_id):
        if input_id in self.input_output_mappings:
            mapping = self.input_output_mappings[input_id]
            if mapping['behavior'] == 'On_while_pressed':
                self.relays[mapping['output']].value(0)
                mapping['active'] = False

    def _init_buttons(self):
        button_pins = [18, 20, 21, 22]
        buttons = []
        for pin in button_pins:
            button = Pin(pin, Pin.IN, Pin.PULL_UP)
            button.irq(trigger=Pin.IRQ_FALLING, handler=self._button_handler)
            buttons.append(button)
        return buttons

    def _button_handler(self, pin):
        for i, button in enumerate(self.buttons):
            if button is pin:
                for callback in self.button_callbacks[i]:
                    callback(i + 1)  # Pass button_id (1-indexed) to callback
                break

    def _setup_mappings(self):
        for input_id, config in self.input_config.items():
            relay_name, duration, behavior = config
            relay_id = self._get_relay_id_by_name(relay_name)
            self.register_input_output_mapping(input_id, relay_id, behavior, duration)

    def _get_relay_id_by_name(self, name):
        for relay_id, relay_name in self.relay_config.items():
            if relay_name == name:
                return relay_id
        raise ValueError(f"No relay found with name: {name}")

    def register_input_output_mapping(self, input_id, output_id, behavior, duration=None):
        print(input_id, output_id, behavior)
        self.input_output_mappings[input_id] = {
            'output': output_id,
            'behavior': behavior,
            'duration': duration,
            'active': False,
            'timer_task': None
        }

    def switch_relay(self, relay_id, duration_ms, timer_task=None):
        print(relay_id, duration_ms)
        if isinstance(relay_id, str):
            relay_id = self._get_relay_id_by_name(relay_id)
        if relay_id in self.relays:
            if self.relays[relay_id].value():
                self.relays[relay_id].value(0)  # Turn off the relay
                if timer_task:
                    timer_taskHi .cancel()
            else:
                self.relays[relay_id].value(1)  # Turn on the relay
            if duration_ms:
                self.timers[relay_id] = duration_ms
                uasyncio.create_task(self.run_timer(relay_id, duration_ms))
        else:
            raise ValueError("Invalid relay ID")

    async def run_timer(self, relay_id, duration):
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < duration:
            await uasyncio.sleep_ms(100)
        self.relays[relay_id].value(0)
        self.timers[relay_id] = 0
        for mapping in self.input_output_mappings.values():
            if mapping['output'] == relay_id:
                mapping['active'] = False
                mapping['timer_task'] = None

    def get_relay_time_left(self, relay_id):
        if 0 <= relay_id < 8:
            return self.timers[relay_id]
        else:
            raise ValueError("Invalid relay ID")

    def register_button_callback(self, button_id, callback):
        _button_id = button_id -1
        if 0 <= _button_id < 4:
            self.button_callbacks[_button_id].append(callback)
        else:
            raise ValueError("Invalid button ID")

    @property
    def relay_states(self):
        self._relay_states = [relay.value() for relay in self.relays]
        return self._relay_states

    def generate_relay_json(self):
        relay_data = {
            f"relay{i+1}": {
                "state": int(state),
                "name": self.names[i],
                "delay": self.delays[i]
            } for i, state in enumerate(self.relay_states)
        }
        return ujson.dumps(relay_data)
    
async def main():
    dn33c08 = DN33C08()
    uasyncio.create_task(dn33c08.process_input_queue())
    while True:
        await uasyncio.sleep(1)

if __name__ == "__main__":
    uasyncio.run(main())
