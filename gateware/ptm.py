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

class TLPWordAligner(LiteXModule):
    """RX Word Aligner

    Align RX Words by analyzing the location of the COM/K-codes (configurable) in the RX stream.
    """
    def __init__(self, check_ctrl_only=False):
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
                    If(sink.ctrl[i] & (check_ctrl_only | (sink.data[8*i:8*(i+1)] == SHP.value)),
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
        self.comb += If(source.valid, Case(alignment_d, cases))


class PTMResponseSnifferInjector(LiteXModule):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", 32)])

        # # #

        data_count = Signal(8)
        data_last  = Signal(32)

        # PTM Response Sniffer.
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            sink.ready.eq(1),
            If((sink.valid &
               (sink.data[0*8:1*8] == 0xfb) & (sink.ctrl[0] == 1) &
                                              (sink.ctrl[1] == 0) &
                                              (sink.ctrl[2] == 0) &
               (sink.data[3*8:4*8] == 0x74) & (sink.ctrl[3] == 0)),
                NextValue(data_last, sink.data),
                NextValue(data_count, 0),
                NextState("RECEIVE")
            )
        )
        fsm.act("RECEIVE",
            sink.ready.eq(1),
            If(sink.valid,
                source.valid.eq(1),
                source.data[8*0:8*1].eq(data_last[24:32]),
                source.data[8*1:8*2].eq(sink.data[8*0:8*1]),
                source.data[8*2:8*3].eq(sink.data[8*1:8*2]),
                source.data[8*3:8*4].eq(sink.data[8*2:8*3]),
                NextValue(data_last, sink.data),
                NextValue(data_count, data_count + 1),
                If(data_count == 4,
                    NextState("CRC")

                )
            )
        )
        fsm.act("CRC",
            sink.ready.eq(1),
            If(sink.valid,
                NextState("IDLE")
            )
        )
