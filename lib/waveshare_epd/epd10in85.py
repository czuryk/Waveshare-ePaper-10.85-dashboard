# *****************************************************************************
# * | File        :	  epd5in79.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.0
# * | Date        :   2024-03-05
# # | Info        :   python demo
# -----------------------------------------------------------------------------
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#


import logging
import time
from PIL import Image
from . import epdconfig

# Display resolution
EPD_WIDTH       = 1360      #  WIDTH = 1360/2
EPD_HEIGHT      = 480

logger = logging.getLogger(__name__)

class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_m_pin = epdconfig.CS_M_PIN
        self.cs_s_pin = epdconfig.CS_S_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.partFlag0 = 0
        self.partFlag1 = 0

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200) 
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)   

    def send_command_M(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_m_pin, 0)
        epdconfig.spi_writebyte_M([command])
        epdconfig.digital_write(self.cs_m_pin, 1)

    def send_command_S(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_s_pin, 0)
        epdconfig.spi_writebyte_S([command])
        epdconfig.digital_write(self.cs_s_pin, 1)

    def send_command_ALL(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_m_pin, 0)
        epdconfig.digital_write(self.cs_s_pin, 0)
        epdconfig.spi_writebyte_M([command])
        epdconfig.spi_writebyte_S([command])
        epdconfig.digital_write(self.cs_m_pin, 1)
        epdconfig.digital_write(self.cs_s_pin, 0)

    def send_data_M(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_m_pin, 0)
        epdconfig.spi_writebyte_M([data])
        epdconfig.digital_write(self.cs_m_pin, 1)
    
    def send_data_S(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_s_pin, 0)
        epdconfig.spi_writebyte_S([data])
        epdconfig.digital_write(self.cs_s_pin, 1)

    def send_data_ALL(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_m_pin, 0)
        epdconfig.digital_write(self.cs_s_pin, 0)
        epdconfig.spi_writebyte_M([data])
        epdconfig.spi_writebyte_S([data])
        epdconfig.digital_write(self.cs_m_pin, 1)
        epdconfig.digital_write(self.cs_s_pin, 1)

    # send a lot of data   
    def send_data2_M(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_m_pin, 0)
        epdconfig.spi_writebyte2_M(data)
        epdconfig.digital_write(self.cs_m_pin, 1)

    def send_data2_S(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_s_pin, 0)
        epdconfig.spi_writebyte2_S(data)
        epdconfig.digital_write(self.cs_s_pin, 1)
        
    def ReadBusy(self, timeout_s=40):
        # Safety net: never block forever if BUSY never releases. Better to
        # continue (and maybe show one imperfect frame) than to hang the whole
        # process. Partial updates pass a short timeout; full refresh / init
        # legitimately take ~15-20s and use the long default.
        start = time.time()
        deadline = start + timeout_s
        polls = 0
        logger.debug("ReadBusy: waiting for BUSY release (timeout=%ss)", timeout_s)
        while(epdconfig.digital_read(self.busy_pin) == 0):      #  0: busy, 1: idle
            epdconfig.delay_ms(100)
            polls += 1
            if time.time() > deadline:
                logger.warning("ReadBusy: BUSY still LOW after %ss (%d polls) -> TIMEOUT, continuing",
                               timeout_s, polls)
                return False
        logger.debug("ReadBusy: released after %.2fs (%d polls)", time.time() - start, polls)
        return True

    def TurnOnDisplay(self, timeout_s=40):
        self.send_command_ALL(0x12)
        epdconfig.delay_ms(100)	        # The delay here is necessary, 200uS at least!!!
        return self.ReadBusy(timeout_s) # waiting for the electronic paper IC to release the idle signal

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
            
        self.reset()
        self.ReadBusy()           
        self.send_command_ALL(0x4D)  
        self.send_data_ALL(0x55)   

        self.send_command_ALL(0xA6)
        self.send_data_ALL(0x38)

        self.send_command_ALL(0xB4)
        self.send_data_ALL(0x5D)

        self.send_command_ALL(0xB6)
        self.send_data_ALL(0x80)

        self.send_command_ALL(0xB7)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0xF7)
        self.send_data_ALL(0x02)

        self.send_command_ALL(0xAE)
        self.send_data_ALL(0xA0)

        self.send_command_ALL(0xE0)
        self.send_data_ALL(0x01)

        self.send_command_ALL(0x00)
        self.send_data_ALL(0x9F)
        self.send_data_ALL(0x0D)

        self.send_command_ALL(0x06)
        self.send_data_ALL(0x57)
        self.send_data_ALL(0x24)
        self.send_data_ALL(0x28)
        self.send_data_ALL(0x32)
        self.send_data_ALL(0x08)
        self.send_data_ALL(0x48)

        self.send_command_ALL(0x61)
        self.send_data_ALL(0x02)
        self.send_data_ALL(0xA8)
        self.send_data_ALL(0x01)
        self.send_data_ALL(0xE0)

        self.send_command_ALL(0x62)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0x60)
        self.send_data_ALL(0x31)

        self.send_command_ALL(0x50)
        self.send_data_ALL(0x97)

        self.send_command_ALL(0xE8)
        self.send_data_ALL(0x01)


        self.send_command_ALL(0x04)
        epdconfig.delay_ms(200)	     
        self.ReadBusy()    

        return 0

    '''
    # Original
    def init_Part(self):
        if (epdconfig.module_init() != 0):
            return -1
        
        self.partFlag0 = 1
            
        self.reset()
        self.ReadBusy()           
        self.send_command_ALL(0x4D)  
        self.send_data_ALL(0x55)   

        self.send_command_ALL(0xA6)
        self.send_data_ALL(0x38)

        self.send_command_ALL(0xB4)
        self.send_data_ALL(0x5D)

        self.send_command_ALL(0xB6)
        self.send_data_ALL(0x80)

        self.send_command_ALL(0xB7)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0xF7)
        self.send_data_ALL(0x02)

        self.send_command_ALL(0xAE)
        self.send_data_ALL(0xA0)

        self.send_command_ALL(0xE0)
        self.send_data_ALL(0x01)

        self.send_command_ALL(0x00)
        self.send_data_ALL(0x9F)
        self.send_data_ALL(0x0D)

        self.send_command_ALL(0x06)
        self.send_data_ALL(0x57)
        self.send_data_ALL(0x24)
        self.send_data_ALL(0x28)
        self.send_data_ALL(0x32)
        self.send_data_ALL(0x08)
        self.send_data_ALL(0x48)

        self.send_command_ALL(0x61)
        self.send_data_ALL(0x02)
        self.send_data_ALL(0xA8)
        self.send_data_ALL(0x01)
        self.send_data_ALL(0xE0)

        self.send_command_ALL(0x62)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0x82)
        self.send_data_ALL(0x12)

        self.send_command_ALL(0x60)
        self.send_data_ALL(0x31)

        self.send_command_ALL(0x50)
        self.send_data_ALL(0x97)

        self.send_command_ALL(0xE8)
        self.send_data_ALL(0x01)

        self.send_command_ALL(0xE0)
        self.send_data_ALL(0x03)
        self.send_command_ALL(0xE5)
        self.send_data_ALL(0x64)

        self.send_command_ALL(0x04)
        epdconfig.delay_ms(200)	     
        self.ReadBusy()   

        return 0
    '''

    # Fixed
    def init_Part(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.partFlag0 = 1
        self.partFlag1 = 1  # <--- ДОБАВЛЕНО: инициализация флага второго экрана

        self.reset()
        self.ReadBusy()
        self.send_command_ALL(0x4D)
        self.send_data_ALL(0x55)

        self.send_command_ALL(0xA6)
        self.send_data_ALL(0x38)

        self.send_command_ALL(0xB4)
        self.send_data_ALL(0x5D)

        self.send_command_ALL(0xB6)
        self.send_data_ALL(0x80)

        self.send_command_ALL(0xB7)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0xF7)
        self.send_data_ALL(0x02)

        self.send_command_ALL(0xAE)
        self.send_data_ALL(0xA0)

        self.send_command_ALL(0xE0)
        self.send_data_ALL(0x01)

        self.send_command_ALL(0x00)
        self.send_data_ALL(0x9F)
        self.send_data_ALL(0x0D)

        self.send_command_ALL(0x06)
        self.send_data_ALL(0x57)
        self.send_data_ALL(0x24)
        self.send_data_ALL(0x28)
        self.send_data_ALL(0x32)
        self.send_data_ALL(0x08)
        self.send_data_ALL(0x48)

        self.send_command_ALL(0x61)
        self.send_data_ALL(0x02)
        self.send_data_ALL(0xA8)
        self.send_data_ALL(0x01)
        self.send_data_ALL(0xE0)

        self.send_command_ALL(0x62)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)
        self.send_data_ALL(0x00)

        self.send_command_ALL(0x82)
        self.send_data_ALL(0x12)

        self.send_command_ALL(0x60)
        self.send_data_ALL(0x31)

        self.send_command_ALL(0x50)
        self.send_data_ALL(0x97)

        self.send_command_ALL(0xE8)
        self.send_data_ALL(0x01)

        self.send_command_ALL(0xE0)
        self.send_data_ALL(0x03)
        self.send_command_ALL(0xE5)
        self.send_data_ALL(0x64)

        self.send_command_ALL(0x04)
        epdconfig.delay_ms(200)
        self.ReadBusy()

        return 0

    def getbuffer(self, image):
        # Fast path: a PIL image in mode '1' already stores its pixels as
        # packed, MSB-first bits (1 = white, 0 = black), which is exactly the
        # panel's buffer format. image.tobytes() does the packing in C, so it
        # replaces a ~650k-iteration Python loop that is far too slow on a
        # Pi Zero 1 (that loop is what tripped the hardware watchdog).
        if image.mode != '1':
            image = image.convert('1')
        imwidth, imheight = image.size
        if imwidth == self.width and imheight == self.height:
            return bytearray(image.tobytes())
        elif imwidth == self.height and imheight == self.width:
            # Portrait image: rotate it into the panel's landscape orientation.
            return bytearray(image.rotate(90, expand=True).tobytes())
        else:
            # Fallback: paste onto a correctly sized white frame.
            frame = Image.new('1', (self.width, self.height), 255)
            frame.paste(image, (0, 0))
            return bytearray(frame.tobytes())

    def Clear(self):
        self.send_command_M(0x10)
        self.send_data2_M([0xFF] * 40800)
        self.send_command_M(0x13)
        self.send_data2_M([0xFF] * 40800)

        self.send_command_S(0x10)
        self.send_data2_S([0xFF] * 40800)
        self.send_command_S(0x13)
        self.send_data2_S([0xFF] * 40800)

        self.TurnOnDisplay()

    def Clear_Black(self):
        self.send_command_M(0x10)
        self.send_data2_M([0xFF] * 40800)
        self.send_command_M(0x13)
        self.send_data2_M([0x00] * 40800)

        self.send_command_S(0x10)
        self.send_data2_S([0xFF] * 40800)
        self.send_command_S(0x13)
        self.send_data2_S([0x00] * 40800)

        self.TurnOnDisplay()

    def display(self, imageblack):
        Width =int(self.width / 16)

        self.send_command_M(0x10)
        self.send_data2_M([0xFF] * 40800)
        self.send_command_M(0x13)
        for i in range(self.height):
            self.send_data2_M(imageblack[i * Width * 2 : i * Width * 2+Width])

        self.send_command_S(0x10)
        self.send_data2_S([0xFF] * 40800)
        self.send_command_S(0x13)
        for i in range(self.height):
            self.send_data2_S(imageblack[i * Width * 2 + Width : (i+1) * Width * 2])

        self.TurnOnDisplay()

    '''
    def display_Partial(self, Image, Xstart, Ystart, Xend, Yend):
        if((Xstart % 8 + Xend % 8 == 8 & Xstart % 8 > Xend % 8) | Xstart % 8 + Xend % 8 == 0 | (Xend - Xstart)%8 == 0):
            Xstart = Xstart // 8
            Xend = Xend // 8
        else:
            Xstart = Xstart // 8 
            if Xend % 8 == 0:
                Xend = Xend // 8
            else:
                Xend = Xend // 8 + 1

        Width =  Xend -  Xstart
        Height = Yend - Ystart
        IMAGE_COUNTER = Width * Height

        Xend -= 1
        Yend -= 1
        
        if((Xend*8)<self.width//2):
            self.send_command_ALL(0x61)
            self.send_data_ALL(((Width*8)>>8) & 0xff)
            self.send_data_ALL((Width*8) & 0xff)
            self.send_data_ALL((Height>>8) & 0xff)
            self.send_data_ALL(Height & 0xff)
            

            self.send_command_ALL(0x62)
            self.send_data_ALL(((Xstart*8)>>8) & 0xff)
            self.send_data_ALL((Xstart*8) & 0xff)
            self.send_data_ALL((Ystart>>8) & 0xff)
            self.send_data_ALL(Ystart & 0xff)
            

            if self.partFlag0 == 0:
                self.partFlag0 = 1
                self.send_command_M(0x00)
                self.send_data2_M([0xFF] * IMAGE_COUNTER)

            self.send_command_M(0x13)
            self.send_data2_M(Image)

            self.TurnOnDisplay()
            self.send_command_M(0x10)
            self.send_data2_M(Image)
    
        elif((Xstart*8)>self.width//2):
            self.send_command_S(0x61)
            self.send_data_S(((Width*8)>>8) & 0xff)
            self.send_data_S((Width*8) & 0xff)
            self.send_data_S((Height>>8) & 0xff)
            self.send_data_S(Height & 0xff)
            
            self.send_command_S(0x62)
            self.send_data_S(((Xstart*8 - self.width//2)>>8) & 0xff)
            self.send_data_S((Xstart*8 - self.width//2) & 0xff)
            self.send_data_S((Ystart>>8) & 0xff)
            self.send_data_S(Ystart & 0xff)
            

            if self.partFlag1 == 0:
                self.partFlag1 = 1
                self.send_command_S(0x00)
                self.send_data2_S([0xFF] * IMAGE_COUNTER)

            self.send_command_S(0x13)
            self.send_data2_S(Image)

            self.TurnOnDisplay()

            self.send_command_S(0x10)
            self.send_data2_S(Image)

        else:
            Width0 = self.width//16 - Xstart
            Width1 = Xend - self.width//16

            self.send_command_M(0x61)
            self.send_data_M(((Width0*8)>>8) & 0xff)
            self.send_data_M((Width0*8) & 0xff)
            self.send_data_M((Height>>8) & 0xff)
            self.send_data_M(Height& 0xff)

            self.send_command_M(0x62)
            self.send_data_M(((Xstart*8)>>8) & 0x01)
            self.send_data_M((Xstart*8) & 0xff)
            self.send_data_M((Ystart>>8) & 0x01)
            self.send_data_M(Ystart & 0xff)

            self.send_command_S(0x61)
            self.send_data_S(((Width1*8)>>8) & 0xff)
            self.send_data_S((Width1*8) & 0xff)
            self.send_data_S((Height>>8) & 0x01)
            self.send_data_S(Height & 0xff)

            self.send_command_S(0x62)
            self.send_data_S(0x00)
            self.send_data_S(0x00)
            self.send_data_S((Ystart>>8) & 0x01)
            self.send_data_S(Ystart & 0xff)
            

            if self.partFlag0 == 0:
                self.partFlag0 = 1
                self.send_command_M(0x00)
                self.send_data2_M([0xFF] * Height * Width1)

            self.send_command_M(0x13)
            for i in range(self.height):
                self.send_data2_M(Image[i*Width : i*Width+Width0])

            if self.partFlag1 == 0:
                self.partFlag1 = 1
                self.send_command_S(0x00)
                self.send_data2_S([0xFF] * Height * Width0)

            self.send_command_S(0x13)
            for i in range(self.height):
                self.send_data2_S(Image[i*Width+Width0 : i*Width+Width])

            self.TurnOnDisplay()

            self.send_command_M(0x10)
            for i in range(self.height):
                self.send_data2_M(Image[i*Width : i*Width+Width0])

            self.send_command_S(0x10)
            for i in range(self.height):
                self.send_data2_S(Image[i*Width+Width0 : i*Width+Width])
       '''

    '''
    # Fixed A>>B
    def display_Partial(self, Image, Xstart, Ystart, Xend, Yend):
        """
        Partial update for 10.85" (1360x480) panel with 2 controllers:
          - Left half  (M): x = [0 .. width/2-1]
          - Right half (S): x = [width/2 .. width-1]

        IMPORTANT (contract):
          - `Image` must be a 1bpp packed buffer for the updated window ONLY
            (not a full-screen buffer), row-major, MSB-first in each byte.
          - Window coordinates are in pixels: [Xstart, Ystart) .. [Xend, Yend)
          - Xstart/Xend will be internally aligned to byte boundary (8 px).
        """

        # ---- clamp to screen ----
        if Xstart < 0: Xstart = 0
        if Ystart < 0: Ystart = 0
        if Xend > self.width: Xend = self.width
        if Yend > self.height: Yend = self.height
        if Xend <= Xstart or Yend <= Ystart:
            return

        mid = self.width // 2  # 680 for 1360

        # ---- align X to byte boundary (8 pixels) ----
        # Make sure the updated region covers requested pixels.
        Xs = (Xstart // 8) * 8
        Xe = ((Xend + 7) // 8) * 8
        if Xe > self.width:
            Xe = self.width

        Ys = Ystart
        Ye = Yend

        win_w_px = Xe - Xs
        win_h = Ye - Ys
        win_w_bytes = win_w_px // 8

        # Expected input buffer size for the window
        expected = win_w_bytes * win_h
        if len(Image) != expected:
            raise ValueError(
                f"display_Partial: buffer size mismatch. "
                f"Expected {expected} bytes (w={win_w_px}px, h={win_h}), got {len(Image)}"
            )

        # Helper to send a window buffer to one controller
        def _send_to_M(buf, x_px, y_px, w_px, h_px):
            w_bytes = (w_px // 8)
            # Set partial window size
            self.send_command_M(0x61)
            self.send_data_M((w_px >> 8) & 0xFF)
            self.send_data_M(w_px & 0xFF)
            self.send_data_M((h_px >> 8) & 0xFF)
            self.send_data_M(h_px & 0xFF)
            # Set partial window origin (x,y) in this controller coords
            self.send_command_M(0x62)
            self.send_data_M((x_px >> 8) & 0xFF)
            self.send_data_M(x_px & 0xFF)
            self.send_data_M((y_px >> 8) & 0xFF)
            self.send_data_M(y_px & 0xFF)

            # First partial on this controller: feed "old" buffer to avoid artifacts
            if self.partFlag0 == 0:
                self.partFlag0 = 1
                self.send_command_M(0x00)
                self.send_data2_M([0xFF] * (w_bytes * h_px))

            # New image (0x13), then refresh, then copy to old (0x10)
            self.send_command_M(0x13)
            self.send_data2_M(buf)
            self.TurnOnDisplay()
            self.send_command_M(0x10)
            self.send_data2_M(buf)

        def _send_to_S(buf, x_px, y_px, w_px, h_px):
            w_bytes = (w_px // 8)
            self.send_command_S(0x61)
            self.send_data_S((w_px >> 8) & 0xFF)
            self.send_data_S(w_px & 0xFF)
            self.send_data_S((h_px >> 8) & 0xFF)
            self.send_data_S(h_px & 0xFF)

            self.send_command_S(0x62)
            self.send_data_S((x_px >> 8) & 0xFF)
            self.send_data_S(x_px & 0xFF)
            self.send_data_S((y_px >> 8) & 0xFF)
            self.send_data_S(y_px & 0xFF)

            if self.partFlag1 == 0:
                self.partFlag1 = 1
                self.send_command_S(0x00)
                self.send_data2_S([0xFF] * (w_bytes * h_px))

            self.send_command_S(0x13)
            self.send_data2_S(buf)
            self.TurnOnDisplay()
            self.send_command_S(0x10)
            self.send_data2_S(buf)

        # ---- case 1: entirely left (M) ----
        if Xe <= mid:
            _send_to_M(Image, Xs, Ys, win_w_px, win_h)
            return

        # ---- case 2: entirely right (S) ----
        if Xs >= mid:
            # Convert to S-local X coordinate (0..mid-1)
            _send_to_S(Image, Xs - mid, Ys, win_w_px, win_h)
            return

        # ---- case 3: crosses mid -> split into two buffers ----
        # Left part: [Xs .. mid)
        left_w_px = mid - Xs
        left_w_bytes = left_w_px // 8

        # Right part: [mid .. Xe)
        right_w_px = Xe - mid
        right_w_bytes = right_w_px // 8

        # Build left/right buffers row by row from window buffer
        left_buf = bytearray(left_w_bytes * win_h)
        right_buf = bytearray(right_w_bytes * win_h)

        for row in range(win_h):
            row_off = row * win_w_bytes
            l0 = row_off
            l1 = row_off + left_w_bytes
            r0 = l1
            r1 = row_off + win_w_bytes

            left_buf[row * left_w_bytes:(row + 1) * left_w_bytes] = bytes(Image[l0:l1])
            right_buf[row * right_w_bytes:(row + 1) * right_w_bytes] = bytes(Image[r0:r1])

        # Send to each controller with correct local coordinates
        _send_to_M(left_buf, Xs, Ys, left_w_px, win_h)
        _send_to_S(right_buf, 0, Ys, right_w_px, win_h)
    '''

    def display_Partial(self, Image, Xstart, Ystart, Xend, Yend):
        """
        Simultaneous Partial update for 10.85" (1360x480).
        Fixes:
        1. Simultaneous refresh (no delay between screens).
        2. Correct register usage (0x10 for old data) preventing right screen crash.
        """
        # ---- clamp to screen ----
        if Xstart < 0: Xstart = 0
        if Ystart < 0: Ystart = 0
        if Xend > self.width: Xend = self.width
        if Yend > self.height: Yend = self.height
        if Xend <= Xstart or Yend <= Ystart:
            return

        mid = self.width // 2  # 680

        # ---- align X to byte boundary (8 pixels) ----
        Xs = (Xstart // 8) * 8
        Xe = ((Xend + 7) // 8) * 8
        if Xe > self.width:
            Xe = self.width

        Ys = Ystart
        Ye = Yend

        win_w_px = Xe - Xs
        win_h = Ye - Ys
        win_w_bytes = win_w_px // 8

        expected = win_w_bytes * win_h
        if len(Image) != expected:
            # Simple safeguard logic: if buffer is full screen, try to crop logic or raise error.
            # Assuming input Image is exactly size of window requested.
            raise ValueError(f"Buffer mismatch: expected {expected}, got {len(Image)}")

        logger.debug("display_Partial: window x[%d..%d] y[%d..%d] = %dx%dpx, %d bytes, mid=%d",
                     Xs, Xe, Ys, Ye, win_w_px, win_h, expected, mid)

        # --- Helper: Load data into controller RAM (0x13 New Data) ---
        # Does NOT trigger refresh yet.
        def _load_data_M(buf, x_px, y_px, w_px, h_px):
            w_bytes = (w_px // 8)
            self.send_command_M(0x61)  # Set Resolution
            self.send_data_M((w_px >> 8) & 0xFF)
            self.send_data_M(w_px & 0xFF)
            self.send_data_M((h_px >> 8) & 0xFF)
            self.send_data_M(h_px & 0xFF)

            self.send_command_M(0x62)  # Set Window
            self.send_data_M((x_px >> 8) & 0xFF)
            self.send_data_M(x_px & 0xFF)
            self.send_data_M((y_px >> 8) & 0xFF)
            self.send_data_M(y_px & 0xFF)

            # If first partial, clear old memory (Write White to 0x10)
            if self.partFlag0 == 0:
                self.partFlag0 = 1
                self.send_command_M(0x10)  # <--- FIX: 0x10 (Old Data), NOT 0x00
                self.send_data2_M([0xFF] * (w_bytes * h_px))

            self.send_command_M(0x13)  # Write New Data
            self.send_data2_M(buf)

        def _load_data_S(buf, x_px, y_px, w_px, h_px):
            w_bytes = (w_px // 8)
            self.send_command_S(0x61)
            self.send_data_S((w_px >> 8) & 0xFF)
            self.send_data_S(w_px & 0xFF)
            self.send_data_S((h_px >> 8) & 0xFF)
            self.send_data_S(h_px & 0xFF)

            self.send_command_S(0x62)
            self.send_data_S((x_px >> 8) & 0xFF)
            self.send_data_S(x_px & 0xFF)
            self.send_data_S((y_px >> 8) & 0xFF)
            self.send_data_S(y_px & 0xFF)

            # If first partial, clear old memory (Write White to 0x10)
            if self.partFlag1 == 0:
                self.partFlag1 = 1
                self.send_command_S(0x10)  # <--- FIX: 0x10 (Old Data), NOT 0x00
                self.send_data2_S([0xFF] * (w_bytes * h_px))

            self.send_command_S(0x13)  # Write New Data
            self.send_data2_S(buf)

        # --- Helper: Copy New Data to Old Data (0x10) after refresh ---
        def _update_old_M(buf):
            self.send_command_M(0x10)
            self.send_data2_M(buf)

        def _update_old_S(buf):
            self.send_command_S(0x10)
            self.send_data2_S(buf)

        # ==========================================
        # SCENARIO 1: Entirely on Left (Master)
        # ==========================================
        if Xe <= mid:
            _load_data_M(Image, Xs, Ys, win_w_px, win_h)
            self.TurnOnDisplay(timeout_s=12)
            _update_old_M(Image)
            return

        # ==========================================
        # SCENARIO 2: Entirely on Right (Slave)
        # ==========================================
        if Xs >= mid:
            _load_data_S(Image, Xs - mid, Ys, win_w_px, win_h)
            self.TurnOnDisplay(timeout_s=12)
            _update_old_S(Image)
            return

        # ==========================================
        # SCENARIO 3: Crosses Middle (Both)
        # ==========================================

        # 1. Split buffers
        left_w_px = mid - Xs
        left_w_bytes = left_w_px // 8
        right_w_px = Xe - mid
        right_w_bytes = right_w_px // 8

        left_buf = bytearray(left_w_bytes * win_h)
        right_buf = bytearray(right_w_bytes * win_h)

        for row in range(win_h):
            row_off = row * win_w_bytes
            l0 = row_off
            l1 = row_off + left_w_bytes
            r0 = l1
            r1 = row_off + win_w_bytes

            left_buf[row * left_w_bytes: (row + 1) * left_w_bytes] = Image[l0:l1]
            right_buf[row * right_w_bytes: (row + 1) * right_w_bytes] = Image[r0:r1]

        # 2. Load Data to BOTH controllers
        logger.debug("display_Partial[BOTH]: loading M (%d bytes)...", len(left_buf))
        t = time.time()
        _load_data_M(left_buf, Xs, Ys, left_w_px, win_h)
        logger.debug("display_Partial[BOTH]: M loaded in %.2fs; loading S (%d bytes)...",
                     time.time() - t, len(right_buf))
        t = time.time()
        _load_data_S(right_buf, 0, Ys, right_w_px, win_h)  # Slave starts at x=0
        logger.debug("display_Partial[BOTH]: S loaded in %.2fs; refreshing...", time.time() - t)

        # 3. Simultaneous Refresh
        t = time.time()
        ok = self.TurnOnDisplay(timeout_s=12)
        logger.debug("display_Partial[BOTH]: refresh returned %s in %.2fs; writing old-data...",
                     ok, time.time() - t)

        # 4. Update "Old Data" memory for next partial update
        t = time.time()
        _update_old_M(left_buf)
        _update_old_S(right_buf)
        logger.debug("display_Partial[BOTH]: old-data written in %.2fs", time.time() - t)

# ----------------------------------------

    def sleep(self):
        self.send_command_ALL(0x02)
        epdconfig.delay_ms(200)	     
        self.ReadBusy()   

        self.send_command_ALL(0X07) # deep sleep
        self.send_data_ALL(0xA5)
        
        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###

