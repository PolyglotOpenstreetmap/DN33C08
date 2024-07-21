import uasyncio
from machine import Pin

Dot = 0x20

BitsSelection = [
    0xFE, # 1
    0xFD, # 2
    0xFB, # 3
    0xF7, # 4
    ]

DisplayCode = [
    0x00, # 0
    0x00, # 0
    0x00, # 0
    0x00, # 0
    ]

SEG8Code = [
    0x5F, # 0
    0x42, # 1
    0x9B, # 2
    0xD3, # 3
    0xC6, # 4
    0xD5, # 5
    0xDD, # 6
    0x43, # 7
    0xDF, # 8
    0xD7, # 9
    0xCF, # A
    0xDC, # b
    0x1D, # C
    0xDA, # d
    0x9D, # E
    0x8D  # F
    ]

class LED_8SEG():
    def __init__(self, latch=9, clock=10, data=11):
        self.latch = Pin(latch,Pin.OUT)
        self.clock = Pin(clock,Pin.OUT)
        self.data = Pin(data,Pin.OUT)
        self.latch(1)
        self.clock(1)
        self.data(1)
        self.SEG8=SEG8Code
        
    def Send_Bytes(self, dat):
        o = 0
        while(o < 8): 
            if dat & 0x80 == 0x80:
                self.data(1)
            else:
                self.data(0)
            dat = dat << 1  
            self.clock(0)
            self.clock(1)
            o += 1
    '''
    function: Send Command
    parameter: 
        Num: bit select
        Seg：segment select       
    Info:The data transfer
    '''
    def write_cmd(self, Num, Seg):                    
        self.Send_Bytes(Num)
        self.Send_Bytes(Seg)
        self.latch(0)
        self.latch(1)
