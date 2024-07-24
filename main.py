import uasyncio
from WifiConnection import WifiConnection
from DN33C08 import DN33C08
#from MQTTManager import MQTTManager
from Settings import Settings
import ujson

dn33c08 = DN33C08()
mqtt_manager = None

async def handle_client(reader, writer):
    with open('relays_overview.html') as file:
        html = file.read()
    request_line = await reader.readline()
    while await reader.readline() != b"\r\n":
        pass
    request = str(request_line, 'utf-8').split()[1]
    print('Request:', request)
    try:
        if request == '/favicon.ico':
            writer.write(b'HTTP/1.0 404 Not Found\r\n\r\n')
        elif request == '/relay_states':
            writer.write(b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n')
            try:
                json_data = dn33c08.generate_relay_json()
                writer.write(ujson.dumps(json_data).encode())
            except Exception as e:
                import sys
                print("Error in generate_relay_json:")
                sys.print_exception(e)
                writer.write(b'{"error": "Internal server error"}')
        elif request.startswith('/toggle_relay'):
            relay_num = int(request.split('/toggle_relay')[1])
            if 1 <= relay_num <= 8:
                # Find an input that controls this relay
                for input_id, mapping in dn33c08.input_output_mappings.items():
                    if mapping['output'] == relay_num:
                        # Simulate an input activation
                        await dn33c08.handle_input_activation(input_id)
                        writer.write(b'HTTP/1.0 200 OK\r\n\r\n')
                        print(f'Relay {relay_num} toggled via input {input_id}')
                        break
                else:
                    writer.write(b'HTTP/1.0 400 Bad Request\r\n\r\n')
                    print(f'No input found for relay {relay_num}')
            else:
                writer.write(b'HTTP/1.0 400 Bad Request\r\n\r\n')
        elif request.startswith('/update_name'):
            relay_num = int(request.split('/update_name')[1].split('?')[0])
            new_name = request.split('name=')[1]
            if 1 <= relay_num <= 8:
                dn33c08.set_relay_name(relay_num, new_name)
                writer.write(b'HTTP/1.0 200 OK\r\n\r\n')
                print(f'Relay {relay_num} name updated to {new_name}')
            else:
                writer.write(b'HTTP/1.0 400 Bad Request\r\n\r\n')
        else:
            writer.write(b'HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            writer.write(html.encode())
    except Exception as e:
        print(f'Error handling request {request}: {e}')
        writer.write(b'HTTP/1.0 500 Internal Server Error\r\n\r\n')
    finally:
        await writer.drain()
        await writer.wait_closed()
        print('Client Disconnected')

async def run_server():
    while True:
        if WifiConnection.wlan and WifiConnection.wlan.isconnected():
            server = await uasyncio.start_server(handle_client, "0.0.0.0", 80)
            print(f"Server started on {Settings.ip}")
            await server.wait_closed()
        else:
            print("No WiFi connection. Waiting...")
            await uasyncio.sleep_ms(5000)

async def initialize_mqtt():
    global mqtt_manager
    mqtt_manager = MQTTManager(dn33c08, broker=Settings.mqtt_broker, topic_prefix=Settings.mqtt_topic_prefix)
    try:
        mqtt_manager.connect()
        print("MQTT connected")
    except Exception as e:
        print(f"MQTT connection failed: {e}")

async def mqtt_loop():
    while True:
        if mqtt_manager:
            try:
                mqtt_manager.check_msg()
                mqtt_manager.publish_states()
            except Exception as e:
                print(f"MQTT error: {e}")
                # Try to reconnect
                await initialize_mqtt()
        await uasyncio.sleep(1)

async def main():
    dn33c08.update_settings()

    WifiConnection.set_dn33c08(dn33c08)
    
    wifi_task = uasyncio.create_task(WifiConnection.start_and_maintain_connection())

    while not (WifiConnection.wlan and WifiConnection.wlan.isconnected()):
        await uasyncio.sleep(1)
    
    io_task = uasyncio.create_task(dn33c08.process_input_queue())
    server_task = uasyncio.create_task(run_server())
    
    try:
        await uasyncio.gather(io_task, wifi_task, server_task)
    except Exception as e:
        print(f"Error in main loop: {e}")
        import sys
        sys.print_exception(e)
    finally:
        # Clean up tasks
        for task in [wifi_task, server_task]:
            task.cancel()
        await uasyncio.sleep_ms(100)

if __name__ == "__main__":
    uasyncio.run(main())

