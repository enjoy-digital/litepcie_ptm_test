import unittest
import random

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from dumps.dump001 import *

from gateware.serdes import RXDatapath
from gateware.scrambling import Descrambler

def data_generator(dut, length=4096):
    yield dut.source.ready.eq(1)
    rx_data = dump["s7pciephy_debug_rx_data"][:length]
    rx_ctrl = dump["s7pciephy_debug_rx_ctl"][:length]
    for data, ctrl in zip(rx_data, rx_ctrl):
        yield dut.sink.data.eq(data)
        yield dut.sink.ctrl.eq(ctrl)
        yield

class DecodingDUT(LiteXModule):
    def __init__(self):
        self.sink   = stream.Endpoint([("data", 16), ("ctrl", 2)])
        self.source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        self.datapath    = RXDatapath(phy_dw=16)
        self.descrambler = Descrambler()
        self.comb += [
            self.datapath.sink.valid.eq(1),
            self.datapath.sink.data.eq(self.sink.data),
            self.datapath.sink.ctrl.eq(self.sink.ctrl),
            self.datapath.source.connect(self.descrambler.sink),
            self.descrambler.source.connect(self.source),
        ]

class TestDecoding(unittest.TestCase):
    def test_decoding(self):
        dut        = DecodingDUT()
        generators = [
            data_generator(dut),
        ]
        run_simulation(dut, generators, vcd_name="test_decoding.vcd")
