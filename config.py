relays = {  1: 'Hall',
            2: 'Living',
            3: 'Kitchen',
            4: 'Dining',
            5: 'Attic',
            6: 'Cellar',
            7: 'Patio',
            8: 'Toilet'}
inputs = {	1: ['Hall', 12000, "Timed"],
            2: ['Living', 36000, "Timed"],
            3: ['Kitchen', 0, "Toggle"],
            4: ['Dining', 36000, "Timed"],
            5: ['Attic', 36000, "Timed"],
            6: ['Cellar', 36000, "Timed"],
            7: ['Patio', 3600, "Timer_resets"],
            8: ['Toilet', 0, "On_while_pressed"]}
ip = "192.168.1.253"
subnet_mask = "255.255.255.0"
gateway = "192.168.1.1"
dns_server = "8.8.8.8"
mqtt_broker = ""
