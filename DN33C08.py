import uasyncio
import time
from machine import Pin, Timer
from Settings import Settings
from LED_8SEG import LED_8SEG
from queue import Queue

class DN33C08:
    def __init__(self):
        self.debounce = 300
        self.update_settings()
        self.last_press_time = {}
        self.last_release_time = {}
        self.input_queue = Queue(maxsize=20)
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
        print(f"Interrupt triggered for input {input_id}")
        if pin.value() == 0:  # Falling edge (button pressed)
            self.handle_pressed_interrupt(pin, input_id)
        else:  # Rising edge (button released)
            self.handle_released_interrupt(pin, input_id)

    def handle_pressed_interrupt(self, pin, input_id):
        current_time = time.ticks_ms()
        print(current_time - self.last_press_time[input_id], self.debounce, (current_time - self.last_press_time[input_id]) > self.debounce)
        if (current_time - self.last_press_time[input_id]) > self.debounce:
            self.last_press_time[input_id] = current_time
            print(f'putting activate on the queue for {input_id}')
            uasyncio.create_task(self.input_queue.put(('activate', input_id)))

    def handle_released_interrupt(self, pin, input_id):
        current_time = time.ticks_ms()
        if (current_time - self.last_release_time[input_id]) > self.debounce:
            self.last_release_time[input_id] = current_time
            uasyncio.create_task(self.input_queue.put(('deactivate', input_id)))

    async def process_input_queue(self):
        print('starting processing input queue')
        while True:
            try:
                print('in process input queue')
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
                    # If not active, turn on and start timer
                    self.relays[output_id].value(1)
                    if output_id in self.timers:
                        self.timers[output_id].deinit()
                    self.timers[output_id] = Timer(mode=Timer.ONE_SHOT, period=duration, callback=lambda t: self._timer_callback(output_id))
                    mapping['active'] = True
                else:
                    # If already active, turn off and cancel timer
                    self.relays[output_id].value(0)
                    if output_id in self.timers:
                        self.timers[output_id].deinit()
                        self.timers.pop(output_id)
                    mapping['active'] = False
            
            elif behavior == 'Timer_resets':
                self.relays[output_id].value(1)  # Turn on the relay
                if output_id in self.timers:
                    self.timers[output_id].deinit()
                self.timers[output_id] = Timer(mode=Timer.ONE_SHOT, period=duration, callback=lambda t: self._timer_callback(output_id))
                mapping['active'] = True
            
            elif behavior == 'On_while_activated':
                self.relays[output_id].value(1)  # Turn on the relay
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
            try:
                relay_id = self._get_relay_id_by_name(relay_name)
            except ValueError:
                print(f"Warning: No relay found for input {input_id}")
                continue
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

    def switch_relay(self, relay_num, delay):
        # Implement relay switching logic here, including delay handling
        self.relay_states[relay_num] = 1 - self.relay_states[relay_num]
        print(f'Relay {relay_num+1} switched to {"ON" if self.relay_states[relay_num] else "OFF"}')

    def set_relay_name(self, relay_num, name):
        self.relay_names[relay_num] = name
        
    @property
    def relay_states(self):
        print("Accessing relay_states property")
        return [relay.value() for relay in self.relays.values()]

    @property
    def _relay_names(self):
        _relay_names = []
        for relay_id, relay_name in self.relay_config.items():
            _relay_names.append(relay_name)
        return _relay_names

    @property
    def relay_names(self):
        return self._relay_names

    def get_relay_state(self, relay_num):
        print(f"Getting state for relay {relay_num}")
        return self.relays[relay_num].value()

    def get_input_info(self, input_id):
        if input_id in self.input_output_mappings:
            mapping = self.input_output_mappings[input_id]
            output_id = mapping['output']
            return {
                'relay_name': self.relay_names[output_id - 1],
                'behavior': mapping['behavior'],
                'duration': mapping['duration'],
                'active': mapping['active']
            }
        return None

    def generate_relay_json(self):
        print("Entering generate_relay_json")
        result = {}
        for i in range(1, 9):
            print(f"Processing relay {i}")
            relay_info = {
                'name': self.relay_names[i-1],
                'state': self.get_relay_state(i),
                'inputs': []
            }
            for input_id, mapping in self.input_output_mappings.items():
                if mapping['output'] == i:
                    input_info = self.get_input_info(input_id)
                    if input_info:
                        relay_info['inputs'].append({
                            'input_id': input_id,
                            'behavior': input_info['behavior'],
                            'duration': input_info['duration'],
                            'active': input_info['active']
                        })
            result[f'relay{i}'] = relay_info
        return result

    def _timer_callback(self, output_id):
        self.relays[output_id].value(0)  # Turn off the relay
        if output_id in self.timers:
            self.timers[output_id].deinit()
            self.timers.pop(output_id)
        for mapping in self.input_output_mappings.values():
            if mapping['output'] == output_id:
                mapping['active'] = False

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
    
async def main():
    dn33c08 = DN33C08()
    io_task = uasyncio.create_task(dn33c08.process_input_queue())

    if True:
        print(Settings.relays)
        print(Settings.inputs)
        print(Settings.ip)
        print(Settings.subnet_mask)
        print(Settings.gateway)
        print(Settings.dns_server)
        print(Settings.mqtt_broker)
        print(Settings.mqtt_topic_prefix)
     
        print(dn33c08._init_relays())
        print(dn33c08._init_inputs())
        print(dn33c08._init_buttons())
        dn33c08.set_relay_name(7, 'WC')
        #print(dn33c08._get_relay_id_by_name('WC'))
        print(dn33c08._get_relay_id_by_name('Kitchen'))
 
        dn33c08.switch_relay(5, 100000)

        print(dn33c08.relay_states)
        print(dn33c08.relay_names)
        print(dn33c08.get_relay_state(3))
        print(dn33c08.generate_relay_json)
        print(dn33c08.get_timer_remaining(1))

    async def queue_status():
        while True:
            print(f"Queue size: {dn33c08.input_queue.qsize()}")
            await uasyncio.sleep(5)
    queue_status_task = uasyncio.create_task(queue_status())
    try:
        while True:
            await uasyncio.sleep(50)  # Sleep for a long time to keep the script running
    except KeyboardInterrupt:
        print("Program interrupted")

if __name__ == "__main__":
    uasyncio.run(main())

