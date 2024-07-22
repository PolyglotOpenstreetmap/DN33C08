import uasyncio
import time
from machine import Pin, Timer
from Settings import Settings
from LED_8SEG import LED_8SEG
import ujson
from collections import deque

class SimpleQueue:
    def __init__(self, maxsize=20):
        self.queue = deque((), maxsize)
        self._event = uasyncio.Event()

    async def put(self, item):
        if item is None:
            return
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
        self.input_callbacks = {i: [] for i in range(1, 9)}
        self.button_callbacks = {i: [] for i in range(4)}

    def update_settings(self):
        Settings.load_settings()
        self.relay_config = Settings.relays
        self.input_config = Settings.inputs

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
            try:
                item = await self.input_queue.get()
                if item is None:
                    continue
                if not isinstance(item, tuple) or len(item) != 2:
                    continue
                action, input_id = item
                if action == 'activate':
                    await self.handle_input_activation(input_id)
                elif action == 'deactivate':
                    await self.handle_input_deactivation(input_id)
                else:
                    print(f"Unknown action: {action}")
            except Exception as e:
                print(f"Error in process_input_queue: {e}")
                print(f"Error occurred while processing item: {item}")
                # Optionally, add a small delay to prevent tight looping in case of persistent errors
                await uasyncio.sleep_ms(200)

    async def handle_input_activation(self, input_id):
        if input_id in self.input_output_mappings:
            mapping = self.input_output_mappings[input_id]
            output_id = mapping['output']
            behavior = mapping['behavior']
            duration = mapping['duration']

            if behavior == 'Toggle':
                current_state = self.relays[output_id].value()
                self.relays[output_id].value(not current_state)
                if output_id in self.timers:
                    self.timers[output_id].deinit()
                    self.timers.pop(output_id)
            
            elif behavior == 'Timed':
                if not mapping['active']:
                    self.switch_relay(output_id, duration)
                    mapping['active'] = True
                else:
                    self.relays[output_id].value(0)
                    if output_id in self.timers:
                        self.timers[output_id].deinit()
                        self.timers.pop(output_id)
                    mapping['active'] = False
            
            elif behavior == 'Timer_resets':
                self.switch_relay(output_id, duration)
                mapping['active'] = True
            
            elif behavior == 'On_while_activated':
                self.relays[output_id].value(1)
                mapping['active'] = True

        if self.input_callbacks.get(input_id, []):
            for callback in self.input_callbacks.get(input_id, []):
                try:
                    callback(input_id)
                except Exception as e:
                    print(f"Error in activation callback for input {input_id}: {e}")

    async def handle_input_deactivation(self, input_id):
        if input_id in self.input_output_mappings:
            mapping = self.input_output_mappings[input_id]
            if mapping['behavior'] == 'On_while_activated':
                output_id = mapping['output']
                self.relays[output_id].value(0)
                mapping['active'] = False

        if self.input_callbacks.get(input_id, []):
            for callback in self.input_callbacks.get(input_id, []):
                try:
                    callback(input_id)
                except Exception as e:
                    print(f"Error in deactivation callback for input {input_id}: {e}")

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
        self.input_output_mappings[input_id] = {
            'output': output_id,
            'behavior': behavior,
            'duration': duration,
            'active': False,
            'timer_task': None
        }

    def switch_relay(self, relay_id, duration_ms):
        if isinstance(relay_id, str):
            relay_id = self._get_relay_id_by_name(relay_id)
        if relay_id in self.relays:
            self.relays[relay_id].value(1)  # Turn on the relay
            
            # Cancel existing timer if there is one
            if relay_id in self.timers:
                self.timers[relay_id].deinit()
            
            # Create a new timer
            timer = Timer()
            timer.init(mode=Timer.ONE_SHOT, period=duration_ms, callback=lambda t: self._timer_callback(relay_id))
            self.timers[relay_id] = timer
        else:
            raise ValueError("Invalid relay ID")

    def _timer_callback(self, relay_id):
        self.relays[relay_id].value(0)  # Turn off the relay
        self.timers.pop(relay_id, None)
        for mapping in self.input_output_mappings.values():
            if mapping['output'] == relay_id:
                mapping['active'] = False
                mapping['timer_task'] = None

    def get_timer_remaining(self, relay_id):
        if relay_id in self.timers:
            return self.timers[relay_id].time()  # Returns remaining time in milliseconds
        return 0

    def register_input_callback(self, input_id, callback):
        if 1 <= input_id <= 8:
            self.input_callbacks[input_id].append(callback)
        else:
            raise ValueError("Invalid input ID. Must be between 1 and 8.")

    def register_button_callback(self, button_id, callback):
        _button_id = button_id -1
        if 0 <= _button_id < 4:
            self.button_callbacks[_button_id].append(callback)
        else:
            raise ValueError("Invalid button ID")

    @property
    def relay_states(self):
        self._relay_states = [(i, relay.value()) for i, relay in self.relays.items()]
        return self._relay_states

    def generate_relay_json(self):
        relay_data = {}
        for relay_id, relay in self.relays.items():
            relay_name = self.relay_config.get(relay_id, f"Relay {relay_id}")
            state = relay.value()
            remaining = self.get_timer_remaining(relay_id)
            relay_data[f"relay{relay_id}"] = {
                "state": int(state),
                "name": relay_name,
                "remaining": remaining
            }
        return ujson.dumps(relay_data)
    
async def main():
    dn33c08 = DN33C08()
    io_task = uasyncio.create_task(dn33c08.process_input_queue())
    
    # Add other tasks here if needed, for example:
    # display_task = uasyncio.create_task(dn33c08.update_display())
    
    try:
        while True:
            # This keeps the main coroutine running
            # You can add periodic checks or other operations here
            await uasyncio.sleep(1)
    except KeyboardInterrupt:
        print("Program interrupted")
    finally:
        # Clean up tasks if needed
        io_task.cancel()
        # Cancel other tasks here if you've added them
        await io_task
        # Await other cancelled tasks here

if __name__ == "__main__":
    uasyncio.run(main())

