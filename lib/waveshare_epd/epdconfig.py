# /*****************************************************************************
# * | File        :	  epdconfig.py
# * | Author      :   Waveshare team
# * | Function    :   Hardware underlying interface
# * | Info        :
# *----------------
# * | This version:   V1.2
# * | Date        :   2022-10-29
# * | Info        :   
# ******************************************************************************
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

import os
import logging
import sys
import time
import subprocess

from ctypes import *

logger = logging.getLogger(__name__)


class RaspberryPi:
    # Pin definition
    RST_PIN     = 17
    DC_PIN      = 25
    CS_M_PIN    = 8
    CS_S_PIN    = 7
    BUSY_PIN    = 24
    PWR_PIN     = 18
    MOSI_PIN    = 10
    SCLK_PIN    = 11

    def __init__(self):
        import spidev
        import gpiozero
        
        self.SPI_M = spidev.SpiDev()
        self.SPI_S = spidev.SpiDev()
        self.GPIO_RST_PIN    = gpiozero.LED(self.RST_PIN)
        self.GPIO_DC_PIN     = gpiozero.LED(self.DC_PIN)
        # self.GPIO_CS_M_PIN     = gpiozero.LED(self.CS_M_PIN)
        # self.GPIO_CS_M_PIN     = gpiozero.LED(self.CS_M_PIN)
        self.GPIO_PWR_PIN    = gpiozero.LED(self.PWR_PIN)
        # Plain polled level input. Button would enable edge detection we do not
        # need (BUSY is polled in ReadBusy); on a single-core Pi Zero 1 those
        # edge events pile up in the lgpio notify queue and make .value lag,
        # which hangs ReadBusy waiting for a BUSY release that already happened.
        self.GPIO_BUSY_PIN   = gpiozero.DigitalInputDevice(self.BUSY_PIN, pull_up = False)
        # SPI is opened once and kept open; module_init() may be called many
        # times (we re-init the panel before every partial update), and
        # re-opening an already-open spidev leaks file descriptors.
        self._spi_opened = False



    def digital_write(self, pin, value):
        if pin == self.RST_PIN:
            if value:
                self.GPIO_RST_PIN.on()
            else:
                self.GPIO_RST_PIN.off()
        elif pin == self.DC_PIN:
            if value:
                self.GPIO_DC_PIN.on()
            else:
                self.GPIO_DC_PIN.off()
        # elif pin == self.CS_M_PIN:
        #     if value:
        #         self.GPIO_CS_M_PIN.on()
        #     else:
        #         self.GPIO_CS_M_PIN.off()
        # elif pin == self.CS_S_PIN:
        #     if value:
        #         self.GPIO_CS_S_PIN.on()
        #     else:
        #         self.GPIO_CS_S_PIN.off()
        elif pin == self.PWR_PIN:
            if value:
                self.GPIO_PWR_PIN.on()
            else:
                self.GPIO_PWR_PIN.off()

    def digital_read(self, pin):
        if pin == self.BUSY_PIN:
            return self.GPIO_BUSY_PIN.value
        elif pin == self.RST_PIN:
            return self.RST_PIN.value
        elif pin == self.DC_PIN:
            return self.DC_PIN.value
        # elif pin == self.CS_M_PIN:
        #     return self.CS_M_PIN.value
        # elif pin == self.CS_S_PIN:
        #     return self.CS_S_PIN.value
        elif pin == self.PWR_PIN:
            return self.PWR_PIN.value

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte_M(self, data):
        self.SPI_M.writebytes(data)

    def spi_writebyte2_M(self, data):
        self.SPI_M.writebytes2(data)

    def spi_writebyte_S(self, data):
        self.SPI_S.writebytes(data)

    def spi_writebyte2_S(self, data):
        self.SPI_S.writebytes2(data)

    def module_init(self, cleanup=False):
        self.GPIO_PWR_PIN.on()

        # Open SPI only once, even across repeated init/init_Part calls.
        if not self._spi_opened:
            # SPI device, bus = 0, device = 0
            self.SPI_M.open(0, 0)
            self.SPI_M.max_speed_hz = 4000000
            self.SPI_M.mode = 0b00

            self.SPI_S.open(0, 1)
            self.SPI_S.max_speed_hz = 4000000
            self.SPI_S.mode = 0b00

            self._spi_opened = True

        return 0

    def module_exit(self, cleanup=False):
        logger.debug("spi end")
        self.SPI_M.close()
        self.SPI_S.close()
        self._spi_opened = False

        self.GPIO_RST_PIN.off()
        self.GPIO_DC_PIN.off()
        self.GPIO_PWR_PIN.off()
        logger.debug("close 5V, Module enters 0 power consumption ...")
        
        if cleanup:
            self.GPIO_RST_PIN.close()
            self.GPIO_DC_PIN.close()
            # self.GPIO_CS_M_PIN.close()
            # self.GPIO_CS_M_PIN.close()
            self.GPIO_PWR_PIN.close()
            self.GPIO_BUSY_PIN.close()

        



class OrangePi:
    """Orange Pi backend built on libgpiod v2 + spidev.

    RPi.GPIO/gpiozero are Broadcom-specific and will not drive an Allwinner
    board, so this talks to /dev/gpiochip directly. Line numbers are
    board-specific: the values below are for the Orange Pi Zero 2W, whose
    40-pin header carries the same *physical* pin positions as a Pi but wires
    them to different SoC lines. They follow the vendor pin table
    (port base + offset, PH=224, PI=256) and were verified against hardware:

        physical 11 -> PH2  RST      physical 24 -> PH5  CS_M
        physical 12 -> PI1  PWR      physical 26 -> PH9  CS_S
        physical 18 -> PH4  BUSY
        physical 22 -> PI6  DC

    On another Orange Pi model, re-derive these from that board's pin table.
    """

    RST_PIN     = 226
    DC_PIN      = 262
    BUSY_PIN    = 228
    PWR_PIN     = 257
    # Chip selects are asserted by the SPI controller; the driver only reads
    # these attributes, it never drives them as GPIO.
    CS_M_PIN    = 229
    CS_S_PIN    = 233
    GPIOCHIP    = '/dev/gpiochip1'
    SPI_BUS     = 1

    def __init__(self):
        import spidev
        import gpiod
        from gpiod.line import Direction, Value

        self._Value = Value
        self.SPI_M = spidev.SpiDev()
        self.SPI_S = spidev.SpiDev()

        self._req = gpiod.request_lines(
            self.GPIOCHIP,
            consumer='epd10in85',
            config={
                self.RST_PIN: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                self.DC_PIN: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                self.PWR_PIN: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                self.BUSY_PIN: gpiod.LineSettings(direction=Direction.INPUT),
            },
        )
        self._spi_opened = False

    def digital_write(self, pin, value):
        if pin in (self.RST_PIN, self.DC_PIN, self.PWR_PIN):
            self._req.set_value(pin, self._Value.ACTIVE if value else self._Value.INACTIVE)

    def digital_read(self, pin):
        if pin == self.BUSY_PIN:
            return 1 if self._req.get_value(pin) == self._Value.ACTIVE else 0
        return 0

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte_M(self, data):
        self.SPI_M.writebytes(data)

    def spi_writebyte2_M(self, data):
        self.SPI_M.writebytes2(data)

    def spi_writebyte_S(self, data):
        self.SPI_S.writebytes(data)

    def spi_writebyte2_S(self, data):
        self.SPI_S.writebytes2(data)

    def module_init(self, cleanup=False):
        self.digital_write(self.PWR_PIN, 1)

        if not self._spi_opened:
            self.SPI_M.open(self.SPI_BUS, 0)
            self.SPI_M.max_speed_hz = 4000000
            self.SPI_M.mode = 0b00

            self.SPI_S.open(self.SPI_BUS, 1)
            self.SPI_S.max_speed_hz = 4000000
            self.SPI_S.mode = 0b00

            self._spi_opened = True

        return 0

    def module_exit(self, cleanup=False):
        logger.debug("spi end")
        self.SPI_M.close()
        self.SPI_S.close()
        self._spi_opened = False

        self.digital_write(self.RST_PIN, 0)
        self.digital_write(self.DC_PIN, 0)
        self.digital_write(self.PWR_PIN, 0)
        logger.debug("close 5V, Module enters 0 power consumption ...")

        if cleanup:
            self._req.release()


class JetsonNano:
    # Pin definition
    RST_PIN  = 17
    DC_PIN   = 25
    CS_PIN   = 8
    BUSY_PIN = 24
    PWR_PIN  = 18

    def __init__(self):
        import ctypes
        find_dirs = [
            os.path.dirname(os.path.realpath(__file__)),
            '/usr/local/lib',
            '/usr/lib',
        ]
        self.SPI = None
        for find_dir in find_dirs:
            so_filename = os.path.join(find_dir, 'sysfs_software_spi.so')
            if os.path.exists(so_filename):
                self.SPI = ctypes.cdll.LoadLibrary(so_filename)
                break
        if self.SPI is None:
            raise RuntimeError('Cannot find sysfs_software_spi.so')

        import Jetson.GPIO
        self.GPIO = Jetson.GPIO

    def digital_write(self, pin, value):
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        return self.GPIO.input(self.BUSY_PIN)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.SYSFS_software_spi_transfer(data[0])

    def spi_writebyte2(self, data):
        for i in range(len(data)):
            self.SPI.SYSFS_software_spi_transfer(data[i])

    def module_init(self):
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)
        
        self.GPIO.output(self.PWR_PIN, 1)
        
        self.SPI.SYSFS_software_spi_begin()
        return 0

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.SYSFS_software_spi_end()

        logger.debug("close 5V, Module enters 0 power consumption ...")
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)

        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, self.BUSY_PIN, self.PWR_PIN])


class SunriseX3:
    # Pin definition
    RST_PIN  = 17
    DC_PIN   = 25
    CS_PIN   = 8
    BUSY_PIN = 24
    PWR_PIN  = 18
    Flag     = 0

    def __init__(self):
        import spidev
        import Hobot.GPIO

        self.GPIO = Hobot.GPIO
        self.SPI = spidev.SpiDev()

    def digital_write(self, pin, value):
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        return self.GPIO.input(pin)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.writebytes(data)

    def spi_writebyte2(self, data):
        # for i in range(len(data)):
        #     self.SPI.writebytes([data[i]])
        self.SPI.xfer3(data)

    def module_init(self):
        if self.Flag == 0:
            self.Flag = 1
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)

            self.GPIO.output(self.PWR_PIN, 1)
        
            # SPI device, bus = 0, device = 0
            self.SPI.open(2, 0)
            self.SPI.max_speed_hz = 4000000
            self.SPI.mode = 0b00
            return 0
        else:
            return 0

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.close()

        logger.debug("close 5V, Module enters 0 power consumption ...")
        self.Flag = 0
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)

        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, self.BUSY_PIN], self.PWR_PIN)


if sys.version_info[0] == 2:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", shell=True, stdout=subprocess.PIPE)
else:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", shell=True, stdout=subprocess.PIPE, text=True)
output, _ = process.communicate()
if sys.version_info[0] == 2:
    output = output.decode(sys.stdout.encoding)

try:
    with open('/proc/device-tree/model', 'rb') as f:
        model = f.read().decode(errors='ignore')
except OSError:
    model = ''

if "Raspberry" in output:
    implementation = RaspberryPi()
elif "OrangePi" in model or "Orange Pi" in model:
    implementation = OrangePi()
elif os.path.exists('/sys/bus/platform/drivers/gpio-x3'):
    implementation = SunriseX3()
else:
    # Unchanged fallback, but an unrecognised board previously died with a bare
    # "No module named 'Jetson'", which gives no hint that board detection is
    # what actually failed.
    try:
        implementation = JetsonNano()
    except ImportError as e:
        raise RuntimeError(
            f"Unsupported board (device-tree model: {model.strip() or 'unknown'}). "
            f"Detection fell through to the Jetson backend, which is unavailable: {e}"
        )

for func in [x for x in dir(implementation) if not x.startswith('_')]:
    setattr(sys.modules[__name__], func, getattr(implementation, func))

### END OF FILE ###
