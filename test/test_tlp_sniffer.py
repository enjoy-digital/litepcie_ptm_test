import unittest
import random

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from test.dumps.dump_ptm_response001 import *

from gateware.pcie_ptm_sniffer import TLPAligner, TLPEndiannessSwap, TLPFilterFormater

from litepcie.tlp.depacketizer import LitePCIeTLPDepacketizer

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

        self.tlp_aligner         = TLPAligner()
        self.tlp_endianness_swap = TLPEndiannessSwap()
        self.tlp_filter_formater = TLPFilterFormater()
        self.tlp_depacketizer    = LitePCIeTLPDepacketizer(
            data_width   = 64,
            endianness   = "big",
            address_mask = 0,
            capabilities = ["REQUEST", "COMPLETION", "CONFIGURATION", "PTM"],
        )
        self.submodules += stream.Pipeline(
            self.sink,
            self.tlp_aligner,
            self.tlp_endianness_swap,
            self.tlp_filter_formater,
            self.tlp_depacketizer,
        )
        self.comb += [
            self.tlp_depacketizer.req_source.ready.eq(1),
            self.tlp_depacketizer.cmp_source.ready.eq(1),
            self.tlp_depacketizer.conf_source.ready.eq(1),
            self.tlp_depacketizer.ptm_source.ready.eq(1),
        ]

class TestTLPSniffer(unittest.TestCase):
    def test_tlp_sniffer(self):
        dut        = DUT()
        generators = [
            data_generator(dut),
        ]
        run_simulation(dut, generators, vcd_name="test_tlp_sniffer.vcd")
