import unittest
import random

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from test.dumps.dump003 import *

from gateware.pcie_ptm_sniffer import RawDatapath, RawDescrambler

def rx_data_generator(dut, length=8192-1024):
    rx_data = dump["s7pciephy_debug_rx_data"][:length:2]
    rx_ctrl = dump["s7pciephy_debug_rx_ctl"][:length:2]
    for data, ctrl in zip(rx_data, rx_ctrl):
        yield dut.rx_sink.data.eq(data)
        yield dut.rx_sink.ctrl.eq(ctrl)
        yield

@passive
def rx_data_checker(dut, length=4096):
    yield dut.rx_source.ready.eq(1)
    while (yield dut.rx_source.ctrl) != 0xf:
        yield
    f = open("rx_data.bin", "wb")
    while True:
        if (yield dut.rx_source.valid):
            f.write((yield dut.rx_source.data).to_bytes(4, byteorder="little"))
        yield

def tx_data_generator(dut, length=8192-1024):
    tx_data = dump["s7pciephy_debug_tx_data"][:length:2]
    tx_ctrl = dump["s7pciephy_debug_tx_ctl"][:length:2]
    for data, ctrl in zip(tx_data, tx_ctrl):
        yield dut.tx_sink.data.eq(data)
        yield dut.tx_sink.ctrl.eq(ctrl)
        yield

@passive
def tx_data_checker(dut, length=4096):
    yield dut.tx_source.ready.eq(1)
    while (yield dut.tx_source.ctrl) != 0xf:
        yield
    f = open("tx_data.bin", "wb")
    while True:
        if (yield dut.tx_source.valid):
            f.write((yield dut.tx_source.data).to_bytes(4, byteorder="little"))
        yield


class RawSnifferDUT(LiteXModule):
    def __init__(self):
        self.rx_sink   = stream.Endpoint([("data", 16), ("ctrl", 2)])
        self.rx_source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        self.tx_sink   = stream.Endpoint([("data", 16), ("ctrl", 2)])
        self.tx_source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        # RX.
        self.rx_datapath    = RawDatapath(phy_dw=16)
        self.rx_descrambler = RawDescrambler()
        self.comb += [
            self.rx_datapath.sink.valid.eq(1),
            self.rx_datapath.sink.data.eq(self.rx_sink.data),
            self.rx_datapath.sink.ctrl.eq(self.rx_sink.ctrl),
            self.rx_datapath.source.connect(self.rx_descrambler.sink),
            self.rx_descrambler.source.connect(self.rx_source),
        ]

        # TX.
        self.tx_datapath    = RawDatapath(phy_dw=16)
        self.tx_descrambler = RawDescrambler()
        self.comb += [
            self.tx_datapath.sink.valid.eq(1),
            self.tx_datapath.sink.data.eq(self.tx_sink.data),
            self.tx_datapath.sink.ctrl.eq(self.tx_sink.ctrl),
            self.tx_datapath.source.connect(self.tx_descrambler.sink),
            self.tx_descrambler.source.connect(self.tx_source),
        ]

class TestRawSniffer(unittest.TestCase):
    def test_raw_sniffer(self):
        dut        = RawSnifferDUT()
        generators = [
            rx_data_generator(dut),
            tx_data_generator(dut),
            rx_data_checker(dut),
            tx_data_checker(dut),
        ]
        run_simulation(dut, generators, vcd_name="test_raw_sniffer.vcd")
