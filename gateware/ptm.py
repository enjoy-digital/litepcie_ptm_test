#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause


from migen import *

from litex.gen import *
from litex.gen.genlib.misc import WaitTimer

from litex.soc.interconnect import stream

from gateware.common import *

from litepcie.common import phy_layout

# PTM Capabilities Constants -----------------------------------------------------------------------

PTM_STRUCTURE_REGS = 3

PTM_HEADER_REG      = 0x00
PTM_CAPABILITY_REG  = 0x04
PTM_CONTROL_REG     = 0x08

PTM_HEADER_ID_OFFSET      = 0
PTM_HEADER_VERSION_OFFSET = 16

PTM_CAPABILITY_REQUESTER_CAPABLE_OFFSET = 0
PTM_CAPABILITY_RESPONDER_CAPABLE_OFFSET = 1
PTM_CAPABILITY_ROOT_CAPABLE_OFFSET      = 2
PTM_CAPABILITY_CLOCK_GRANULARITY_OFFSET = 8

PTM_CONTROL_ENABLE_OFFSET                = 0
PTM_CONTROL_ROOT_SELECT_OFFSET           = 1
PTM_CONTROL_EFFECTIVE_GRANULARITY_OFFSET = 8

# PTM Capabilities ---------------------------------------------------------------------------------

class PTMCapabilities(LiteXModule):
    def __init__(self, pcie_endpoint,
        requester_capable = True,
        responder_capable = False,
        root_capable      = False,
        clock_granularity = 8e-9,
    ):
        # Outputs.
        self.ptm_enable                = Signal()
        self.ptm_root_select           = Signal()
        self.ptm_effective_granularity = Signal(8)

        # # #

        # Signals.
        reg  = Signal(10)
        dat  = Signal(32)

        # PTM Capability Structure Initial Content.
        ptm_capability_init = {
           PTM_HEADER_REG      : ((1 << PTM_HEADER_VERSION_OFFSET) * 0x01 |
                                  (1 << PTM_HEADER_ID_OFFSET)      * 0x1f),
           PTM_CAPABILITY_REG  : ((1 << PTM_CAPABILITY_REQUESTER_CAPABLE_OFFSET) * requester_capable |
                                  (1 << PTM_CAPABILITY_RESPONDER_CAPABLE_OFFSET) * responder_capable |
                                  (1 << PTM_CAPABILITY_ROOT_CAPABLE_OFFSET)      * root_capable      |
                                  (1 << PTM_CAPABILITY_CLOCK_GRANULARITY_OFFSET) * int(clock_granularity*1e9)),
           PTM_CONTROL_REG     : ((1 << PTM_CONTROL_ENABLE_OFFSET)                * 0 |
                                  (1 << PTM_CONTROL_ROOT_SELECT_OFFSET)           * 0 |
                                  (1 << PTM_CONTROL_EFFECTIVE_GRANULARITY_OFFSET) * 0),
        }

        # PTM Capability Structure Memory.
        mem = Memory(32, PTM_STRUCTURE_REGS, init=[ptm_capability_init[4*i] for i in range(PTM_STRUCTURE_REGS)])
        mem_wr_port   = mem.get_port(write_capable=True)
        mem_rd_port   = mem.get_port(async_read=True)
        mem_ctrl_port = mem.get_port(async_read=True)
        self.specials += mem, mem_wr_port, mem_rd_port, mem_ctrl_port

        # PTM Capability Configuration/Completion Endpoints
        self.conf_ep = conf_ep = pcie_endpoint.depacketizer.conf_source
        self.comp_ep = comp_ep = pcie_endpoint.crossbar.get_slave_port(address_decoder=lambda a: 0).source

        # PTM Capability FSM.
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(conf_ep.valid,
                If(conf_ep.we,
                    NextState("WRITE-MEM")
                ).Else(
                    NextState("READ-MEM")
                )
            )
        )
        self.comb += reg.eq((Cat(conf_ep.register_no, conf_ep.ext_reg) - 0x6B)) # FIXME: Expose.
        fsm.act("WRITE-MEM",
            conf_ep.ready.eq(1),
            mem_wr_port.adr.eq(reg),
            mem_wr_port.we.eq(1),
            mem_wr_port.dat_w.eq(conf_ep.dat),
            NextState("IDLE")
        )
        fsm.act("READ-MEM",
            mem_rd_port.adr.eq(reg),
            NextValue(dat, mem_rd_port.dat_r),
            NextState("SEND-COMPLETION")
        )

        fsm.act("SEND-COMPLETION",
            comp_ep.valid.eq(1),
            comp_ep.first.eq(1),
            comp_ep.last.eq(1),
            comp_ep.len.eq(1),
            comp_ep.err.eq(0),
            comp_ep.tag.eq(conf_ep.tag),
            comp_ep.adr.eq(0),
            comp_ep.cmp_id.eq(pcie_endpoint.phy.id),
            comp_ep.req_id.eq(conf_ep.req_id),
            comp_ep.dat.eq(dat),
            If(comp_ep.valid & comp_ep.ready,
                conf_ep.ready.eq(1),
                NextState("IDLE")
            )
        )

        # PTM Control Outputs.
        self.comb += [
            mem_ctrl_port.adr.eq(PTM_CONTROL_REG//4),
            self.ptm_enable.eq(               (mem_ctrl_port.dat_r >> PTM_CONTROL_ENABLE_OFFSET)                & 0b1),
            self.ptm_root_select.eq(          (mem_ctrl_port.dat_r >> PTM_CONTROL_ROOT_SELECT_OFFSET)           & 0b1),
            self.ptm_effective_granularity.eq((mem_ctrl_port.dat_r >> PTM_CONTROL_EFFECTIVE_GRANULARITY_OFFSET) & 0b1111_1111),
        ]

# PTM Core Constants -------------------------------------------------------------------------------

PTM_REQUEST_MESSAGE_CODE   = 0b01010010 # PTM Request.
PTM_RESPONSE_MESSAGE_CODE  = 0b01010011 # PTM Response without timing information.
PTM_RESPONSED_MESSAGE_CODE = 0b01010011 # PTM Response with timing information.

# PTM Core -----------------------------------------------------------------------------------------

class PTMCore(LiteXModule):
    def __init__(self, pcie_endpoint, sys_clk_freq):
        # Input.
        self.ptm_enable = Signal()

        # # #

        # PTM Request Endpoint.
        self.req_ep = req_ep = pcie_endpoint.packetizer.ptm_sink

        # PTM Request Timer.
        self.req_timer = req_timer = WaitTimer(1*sys_clk_freq)
        self.comb += req_timer.wait.eq(~req_timer.done)

        # PTM Request FSM.
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(self.ptm_enable & req_timer.done,
                NextState("REQUEST")
            )
        )
        fsm.act("REQUEST",
            req_ep.valid.eq(1),
            req_ep.request.eq(1),
            req_ep.response.eq(0),
            req_ep.first.eq(1),
            req_ep.last.eq(1),
            req_ep.length.eq(0),
            req_ep.requester_id.eq(pcie_endpoint.phy.id),
            req_ep.message_code.eq(PTM_REQUEST_MESSAGE_CODE),
            If(req_ep.ready,
                NextState("IDLE")
            )
        )

# PTM Response Sniffer/Injector --------------------------------------------------------------------

class PTMTLPAligner(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

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
                NextState("RECEIVE-1")
            )
        )
        fsm.act("RECEIVE-1",
            If(sink.valid,
                source.valid.eq(1),
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
            If(sink.valid,
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

# PTM TLP to AXI -----------------------------------------------------------------------------------

class PTMTLP2AXI(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint(phy_layout(64))

        # # #

        self.conv = conv = stream.StrideConverter(
            description_from = phy_layout(32),
            description_to   = phy_layout(64),
            reverse          = False
        )
        self.comb += conv.source.connect(self.source)

        self.comb += sink.ready.eq(1)

        count = Signal(32)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(sink.valid,
                # 3 DWs + 32-bit Data.
                If(sink.data[0:8] == 0x34,
                    conv.sink.valid.eq(1),
                    conv.sink.dat.eq(reverse_bytes(sink.data)),
                    conv.sink.be.eq(0b1111),
                    NextValue(count, 3 - 1),
                    NextState("RECEIVE")
                # 4 DWs + 32-bit Data.
                ).Elif(sink.data[0:8] == 0x74,
                    conv.sink.valid.eq(1),
                    conv.sink.dat.eq(reverse_bytes(sink.data)),
                    conv.sink.be.eq(0b1111),
                    NextValue(count, 4 - 1),
                    NextState("RECEIVE")
                ).Else(
                    NextState("END")
                )
            )
        )
        fsm.act("RECEIVE",
            If(sink.valid,
                conv.sink.valid.eq(1),
                conv.sink.dat.eq(reverse_bytes(sink.data)),
                conv.sink.be.eq(0b1111),
                NextValue(count, count - 1),
                If(count == 0,
                    conv.sink.last.eq(1),
                    NextState("END")
                ),
                If(sink.last,
                    conv.sink.last.eq(1),
                    NextState("IDLE")
                )
            )
        )
        fsm.act("END",
            If(sink.valid & sink.last,
                NextState("IDLE")
            )
        )
