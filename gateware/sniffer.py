#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2019-2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from litepcie.common import phy_layout
from litepcie.tlp.common import fmt_type_dict

from gateware.common import COM, EndiannessSwap

# Raw Word Aligner ---------------------------------------------------------------------------------

class RawWordAligner(LiteXModule):
    """Raw Word Aligner

    Align RX Words by analyzing the location of the COM/K-codes (configurable) in the RX stream.
    """
    def __init__(self):
        self.enable = Signal(reset=1)
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        update      = Signal()
        alignment   = Signal(2)
        alignment_d = Signal(2)

        buf = stream.Buffer([("data", 32), ("ctrl", 4)])
        self.submodules += buf
        self.comb += [
            sink.connect(buf.sink),
            source.valid.eq(sink.valid & buf.source.valid),
            buf.source.ready.eq(sink.valid & source.ready),
        ]

        # Alignment detection
        for i in reversed(range(4)):
            self.comb += [
                If(sink.valid & sink.ready,
                    If(sink.ctrl[i] & (sink.data[8*i:8*(i+1)] == COM.value),
                        update.eq(1),
                        alignment.eq(i)
                    )
                )
            ]
        self.sync += [
            If(sink.valid & sink.ready,
                If(self.enable & update,
                    alignment_d.eq(alignment)
                )
            )
        ]

        # Data selection
        data = Cat(buf.source.data, sink.data)
        ctrl = Cat(buf.source.ctrl, sink.ctrl)
        cases = {}
        for i in range(4):
            cases[i] = [
                source.data.eq(data[8*i:]),
                source.ctrl.eq(ctrl[1*i:]),
            ]
        self.comb += Case(alignment_d, cases)

# Raw Datapath -------------------------------------------------------------------------------------

class RawDatapath(LiteXModule):
    """Raw Datapath

    This module realizes the:
    - Data-width adaptation (from transceiver's data-width to 32-bit).
    - Clock domain crossing (from transceiver's RX clock to system clock).
    - Words alignment.

    """
    def __init__(self, clock_domain="sys", phy_dw=16):
        self.sink   = stream.Endpoint([("data", phy_dw), ("ctrl", phy_dw//8)])
        self.source = stream.Endpoint([("data",     32), ("ctrl",         4)])

        # # #

        # Data-width adaptation
        converter = stream.StrideConverter(
            [("data", phy_dw), ("ctrl", phy_dw//8)],
            [("data",     32), ("ctrl",         4)],
            reverse=False)
        converter = stream.BufferizeEndpoints({"sink":   stream.DIR_SINK})(converter)
        converter = ClockDomainsRenamer(clock_domain)(converter)
        self.converter = converter

        # Clock domain crossing
        cdc = stream.AsyncFIFO([("data", 32), ("ctrl", 4)], 8, buffered=True)
        cdc = ClockDomainsRenamer({"write": clock_domain, "read": "sys"})(cdc)
        self.cdc = cdc

        # Words alignment
        word_aligner = RawWordAligner()
        word_aligner = stream.BufferizeEndpoints({"source": stream.DIR_SOURCE})(word_aligner)
        self.word_aligner = word_aligner

        # Flow
        self.submodules += stream.Pipeline(
            self.sink,
            converter,
            cdc,
            word_aligner,
            self.source,
        )

# TLP Aligner --------------------------------------------------------------------------------------

class TLPAligner(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        first        = Signal()
        alignment    = Signal(2)
        sink_ctrl_d  = Signal(4)
        sink_ctrl_dd = Signal(4)
        sink_data_d  = Signal(32)
        sink_data_dd = Signal(32)

        self.comb += sink.ready.eq(1)
        self.sync += [
            If(sink.valid,
                sink_data_d.eq(sink.data),
                sink_data_dd.eq(sink_data_d),
                sink_ctrl_d.eq(sink.ctrl),
                sink_ctrl_dd.eq(sink_ctrl_d)
            )
        ]

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(sink.valid,
                If(sink.ctrl[0] & (sink.data[0*8:1*8] == 0xfb),
                   NextValue(alignment, 0b00),
                   NextState("RECEIVE-0")
                ),
                If(sink.ctrl[1] & (sink.data[1*8:2*8] == 0xfb),
                   NextValue(alignment, 0b01),
                   NextState("RECEIVE-0")
                ),
                If(sink.ctrl[2] & (sink.data[2*8:3*8] == 0xfb),
                   NextValue(alignment, 0b10),
                   NextState("RECEIVE-0")
                ),
                If(sink.ctrl[3] & (sink.data[3*8:4*8] == 0xfb),
                   NextValue(alignment, 0b11),
                   NextState("RECEIVE-0")
                )
            ),
        )
        fsm.act("RECEIVE-0",
            If(sink.valid,
                NextValue(first, 1),
                NextState("RECEIVE-1")
            )
        )
        fsm.act("RECEIVE-1",
            If(sink.valid,
                source.valid.eq(1),
                NextValue(first, 0),
                Case(alignment, {
                    0b00 : [
                        source.data[8*0:8*1].eq(sink_data_dd[8*3:8*4]),
                        source.data[8*1:8*2].eq(sink_data_d [8*0:8*1]),
                        source.data[8*2:8*3].eq(sink_data_d [8*1:8*2]),
                        source.data[8*3:8*4].eq(sink_data_d [8*2:8*3]),
                        source.ctrl[0].eq(sink_ctrl_dd[3]),
                        source.ctrl[1].eq(sink_ctrl_d [0]),
                        source.ctrl[2].eq(sink_ctrl_d [1]),
                        source.ctrl[3].eq(sink_ctrl_d [2]),
                    ],
                    0b01 : [
                        source.data[8*0:8*1].eq(sink_data_d[8*0:8*1]),
                        source.data[8*1:8*2].eq(sink_data_d[8*1:8*2]),
                        source.data[8*2:8*3].eq(sink_data_d[8*2:8*3]),
                        source.data[8*3:8*4].eq(sink_data_d[8*3:8*4]),
                        source.ctrl[0].eq(sink_ctrl_d[0]),
                        source.ctrl[1].eq(sink_ctrl_d[1]),
                        source.ctrl[2].eq(sink_ctrl_d[2]),
                        source.ctrl[3].eq(sink_ctrl_d[3]),
                    ],
                    0b10 : [
                        source.data[8*0:8*1].eq(sink_data_d[8*1:8*2]),
                        source.data[8*1:8*2].eq(sink_data_d[8*2:8*3]),
                        source.data[8*2:8*3].eq(sink_data_d[8*3:8*4]),
                        source.data[8*3:8*4].eq(sink.data  [8*0:8*1]),
                        source.ctrl[0].eq(sink_ctrl_d[1]),
                        source.ctrl[1].eq(sink_ctrl_d[2]),
                        source.ctrl[2].eq(sink_ctrl_d[3]),
                        source.ctrl[3].eq(sink.ctrl  [0]),
                    ],
                    0b11 : [
                        source.data[8*0:8*1].eq(sink_data_d[8*2:8*3]),
                        source.data[8*1:8*2].eq(sink_data_d[8*3:8*4]),
                        source.data[8*2:8*3].eq(sink.data  [8*0:8*1]),
                        source.data[8*3:8*4].eq(sink.data  [8*1:8*2]),
                        source.ctrl[0].eq(sink_ctrl_d[2]),
                        source.ctrl[1].eq(sink_ctrl_d[3]),
                        source.ctrl[2].eq(sink.ctrl  [0]),
                        source.ctrl[3].eq(sink.ctrl  [1]),
                    ],
                }),
            ),
            If(sink.valid & ~first,
                If(sink_ctrl_dd[0] & (sink_data_dd[0*8:1*8] == 0xfd),
                   source.last.eq(1),
                   NextState("IDLE")
                ),
                If(sink_ctrl_dd[1] & (sink_data_dd[1*8:2*8] == 0xfd),
                   source.last.eq(1),
                   NextState("IDLE")
                ),
                If(sink_ctrl_dd[2] & (sink_data_dd[2*8:3*8] == 0xfd),
                   source.last.eq(1),
                   NextState("IDLE")
                ),
                If(sink_ctrl_dd[3] & (sink_data_dd[3*8:4*8] == 0xfd),
                   source.last.eq(1),
                   NextState("IDLE")
                )
            ),
        )


# TLP Endianness Swap ------------------------------------------------------------------------------

class TLPEndiannessSwap(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        self.submodules += EndiannessSwap(sink, source)

# TLP Filter/Formater ------------------------------------------------------------------------------

class TLPFilterFormater(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint(phy_layout(64))

        # # #

        # Signals.
        count = Signal(32)

        # Always accept incoming data.
        self.comb += sink.ready.eq(1)

        # Data-FIFO (For eventual source unavailability absorbtion).
        self.fifo = fifo = stream.SyncFIFO(phy_layout(32), depth=4, buffered=True)

        # Data-Width Converter: 32-bit to 64-bit.
        self.conv = conv = stream.StrideConverter(
            description_from = phy_layout(32),
            description_to   = phy_layout(64),
            reverse          = False
        )
        self.comb += [
            fifo.sink.be.eq(0b1111),
            fifo.source.connect(conv.sink),
            conv.source.connect(self.source),
        ]

        # FSM.
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(sink.valid,
                # PTM Request.
                If(sink.data[24:32] == fmt_type_dict["ptm_req"],
                    fifo.sink.valid.eq(1),
                    fifo.sink.dat.eq(sink.data),
                    NextValue(count, 3 - 1), # 3DWs Header.
                    NextState("RECEIVE")
                # PTM Response.
                ).Elif(sink.data[24:32] == fmt_type_dict["ptm_res"],
                    fifo.sink.valid.eq(1),
                    fifo.sink.dat.eq(sink.data),
                    NextValue(count, 4 - 1), # 4DWs Header.
                    NextState("RECEIVE")
                ).Else(
                    NextState("END")
                )
            )
        )
        fsm.act("RECEIVE",
            If(sink.valid,
                fifo.sink.valid.eq(1),
                fifo.sink.dat.eq(sink.data),
                NextValue(count, count - 1),
                If(count == 0,
                    fifo.sink.last.eq(1),
                    NextState("END")
                ),
                If(sink.last,
                    fifo.sink.last.eq(1),
                    NextState("IDLE")
                )
            )
        )
        fsm.act("END",
            If(sink.valid & sink.last,
                NextState("IDLE")
            )
        )
