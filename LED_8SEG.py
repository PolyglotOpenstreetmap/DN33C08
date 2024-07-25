from machine import Pin, Timer

class LED_8SEG:
    def __init__(self, latch=9, clock=10, data=11):
        self.latch = Pin(latch, Pin.OUT)
        self.clock = Pin(clock, Pin.OUT)
        self.data = Pin(data, Pin.OUT)
        self.latch(1)
        self.clock(1)
        self.data(1)
        
        self.Dot = 0x20
        self.BitsSelection = [0xFE, 0xFD, 0xFB, 0xF7]
        self.char_to_segments = {
            '0': 0x5F, '1': 0x42, '2': 0x9B, '3': 0xD3, '4': 0xC6,
            '5': 0xD5, '6': 0xDD, '7': 0x43, '8': 0xDF, '9': 0xD7,
            'A': 0xCF, 'B': 0xDC, 'C': 0x1D, 'D': 0xDA, 'E': 0x9D,
            'F': 0x8D, 'G': 0xDD, 'H': 0xCE, 'I': 0x42, 'J': 0x52,
            'K': 0xCE, 'L': 0x1C, 'M': 0x4F, 'N': 0xC6, 'O': 0x5F,
            'P': 0x8F, 'Q': 0xD7, 'R': 0x86, 'S': 0xD5, 'T': 0x1E,
            'U': 0x5E, 'V': 0x5E, 'W': 0x5E, 'X': 0xCE, 'Y': 0xD6,
            'Z': 0x9B,
            'a': 0xDB, 'b': 0xDC, 'c': 0x98, 'd': 0xDA, 'e': 0x9F,
            'f': 0x8E, 'g': 0xD7, 'h': 0xCC, 'i': 0x40, 'j': 0x52,
            'k': 0xCE, 'l': 0x1C, 'm': 0x4F, 'n': 0xC4, 'o': 0xD8,
            'p': 0x8F, 'q': 0xC7, 'r': 0x84, 's': 0xD5, 't': 0x1E,
            'u': 0x58, 'v': 0x58, 'w': 0x58, 'x': 0xCE, 'y': 0xD6,
            'z': 0x9B,
            '-': 0x80, ' ': 0x00
        }
        self.buffer = [0] * 4
        self.refresh_timer = Timer(-1)
        self.clear_timer = Timer(-1)
        self.current_content = ""
        self.current_dots = ""

    def Send_Bytes(self, dat):
        for _ in range(8):
            self.data(1 if dat & 0x80 else 0)
            dat <<= 1
            self.clock(0)
            self.clock(1)

    def write_cmd(self, Num, Seg):
        self.Send_Bytes(Num)
        self.Send_Bytes(Seg)
        self.latch(0)
        self.latch(1)

    def set_buffer(self, content, dots):
        self.current_content = content
        self.current_dots = dots
        for i in range(4):
            if i < len(content):
                char = content[i]
                self.buffer[i] = self.char_to_segments.get(char, 0)
            else:
                self.buffer[i] = 0

            if i < len(dots) and dots[i] == '.':
                self.buffer[i] |= self.Dot

    def start_refresh(self):
        self.refresh_timer.init(period=5, mode=Timer.PERIODIC, callback=lambda t: self.update_display())

    def stop_refresh(self):
        self.refresh_timer.deinit()

    def update_display(self):
        for i in range(4):
            self.write_cmd(self.BitsSelection[i], self.buffer[i])

    def clear(self):
        self.buffer = [0] * 4
        self.current_content = ""
        self.current_dots = ""
        self.update_display()

    def set_display(self, content, dots, duration_ms):
        self.clear_timer.deinit()  # Cancel any existing clear timer
        self.set_buffer(content, dots)
        self.start_refresh()  # Start continuous refresh

        if duration_ms > 0:
            self.clear_timer.init(mode=Timer.ONE_SHOT, period=duration_ms, callback=lambda t: self.clear_and_stop())

    def clear_and_stop(self):
        self.clear()
        self.stop_refresh()

    def get_current_display(self):
        return self.current_content, self.current_dots
