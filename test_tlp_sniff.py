import unittest
import random

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from dumps.dump_ptm_response001 import *

from gateware.ptm import PTMTLPAligner

def data_generator(dut, length=4096-1024):
    valid = dump["ptmtlpaligner_sink_valid"][:length:2]
    data  = dump["ptmtlpaligner_sink_payload_data"][:length:2]
    ctrl  = dump["ptmtlpaligner_sink_payload_ctrl"][:length:2]
    for valid, data, ctrl in zip(valid, data, ctrl):
        yield dut.sink.valid.eq(valid)
        yield dut.sink.data.eq(data)
        yield dut.sink.ctrl.eq(ctrl)
        yield


class DUT(LiteXModule):
    def __init__(self):
        self.sink = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        self.ptm_tlp_aligner = PTMTLPAligner()
        self.comb += [
            self.sink.connect(self.ptm_tlp_aligner.sink),
            self.ptm_tlp_aligner.source.ready.eq(1),
        ]

class TestPTMTLP(unittest.TestCase):
    def test_ptm_tlp(self):
        dut        = DUT()
        generators = [
            data_generator(dut),
        ]
        run_simulation(dut, generators, vcd_name="test_ptm_tlp.vcd")
