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

# PTM Sniffer --------------------------------------------------------------------------------------

class PTMSniffer(LiteXModule):
    def __init__(self, rx_rst_n, rx_clk, rx_data, rx_ctrl):
        self.source = source = stream.Endpoint([("master_time", 64), ("propagation_delay", 32)])
        assert len(rx_data) == 16
        assert len(rx_ctrl) == 2

        # # #

        # Clocking.
        self.cd_sniffer = ClockDomain()
        self.comb += self.cd_sniffer.clk.eq(rx_clk)
        self.comb += self.cd_sniffer.rst.eq(~rx_rst_n)

        # Raw Sniffing.
        from gateware.sniffer import RawDatapath
        from gateware.scrambling import RawDescrambler

        self.raw_datapath    = ClockDomainsRenamer("sniffer")(RawDatapath(phy_dw=16))
        self.raw_descrambler = ClockDomainsRenamer("sniffer")(RawDescrambler())
        self.comb += [
            self.raw_datapath.sink.valid.eq(1),
            self.raw_datapath.sink.data.eq(rx_data),
            self.raw_datapath.sink.ctrl.eq(rx_ctrl),
            self.raw_datapath.source.connect(self.raw_descrambler.sink),
        ]

        # TLP Sniffing.
        from gateware.sniffer import TLPAligner, TLPEndiannessSwap, TLPFilterFormater

        self.tlp_aligner         = ClockDomainsRenamer("sniffer")(TLPAligner())
        self.tlp_endianness_swap = ClockDomainsRenamer("sniffer")(TLPEndiannessSwap())
        self.tlp_filter_formater = ClockDomainsRenamer("sniffer")(TLPFilterFormater())

        self.submodules += stream.Pipeline(
            self.raw_descrambler,
            self.tlp_aligner,
            self.tlp_endianness_swap,
            self.tlp_filter_formater,
        )

        # TLP Depacketizer. FIXME: Direct inject TLPs in LitePCIe through an Arbiter.
        from litepcie.tlp.depacketizer import LitePCIeTLPDepacketizer

        self.tlp_depacketizer = ClockDomainsRenamer("sniffer")(LitePCIeTLPDepacketizer(
            data_width   = 64,
            endianness   = "big",
            address_mask = 0,
            capabilities = ["REQUEST", "COMPLETION", "CONFIGURATION", "PTM"],
        ))
        self.comb += self.tlp_filter_formater.source.connect(self.tlp_depacketizer.sink)
        self.comb += [
            self.tlp_depacketizer.req_source.ready.eq(1),
            self.tlp_depacketizer.cmp_source.ready.eq(1),
            self.tlp_depacketizer.conf_source.ready.eq(1),
        ]

        # TLP CDC.
        self.cdc = cdc = stream.ClockDomainCrossing(
            layout  = [("master_time", 64), ("propagation_delay", 32)],
            cd_from = "sniffer",
            cd_to   = "sys",
        )
        self.comb += [
            self.tlp_depacketizer.ptm_source.connect(cdc.sink, keep={"valid", "ready", "master_time"}),
            cdc.sink.propagation_delay.eq(self.tlp_depacketizer.ptm_source.dat), # CHECKME.
            cdc.source.connect(self.source)
        ]

# PTM Requester/Responder Constants ----------------------------------------------------------------

PTM_REQUEST_MESSAGE_CODE   = 0b01010010 # PTM Request.
PTM_RESPONSE_MESSAGE_CODE  = 0b01010011 # PTM Response without timing information.
PTM_RESPONSED_MESSAGE_CODE = 0b01010011 # PTM Response with timing information.

# PTM Requester ------------------------------------------------------------------------------------

class PTMRequester(LiteXModule):
    def __init__(self, pcie_endpoint, ptm_sniffer, sys_clk_freq):
        # Inputs.
        self.ptm_enable       = Signal()
        self.ptm_trigger      = Signal()
        self.ptm_invalidation = Signal()

        # Outputs.
        self.ptm_valid             = Signal()
        self.ptm_update            = Signal()
        self.ptm_master_time       = Signal(64)
        self.ptm_propagation_delay = Signal(32)

        # # #

        # PTM Request Endpoint.
        self.req_ep = req_ep = pcie_endpoint.packetizer.ptm_sink

        # PTM Response Endpoint.
        self.res_ep = res_ep = ptm_sniffer.source

        # PTM Request Timer.
        self.req_timer = req_timer = WaitTimer(1e-6*sys_clk_freq)

        # PTM Requester FSM.
        self.fsm = fsm = ResetInserter()(FSM(reset_state="IDLE"))
        self.comb += fsm.reset.eq(~self.ptm_enable)
        fsm.act("START",
            If(self.ptm_enable,
                NextState("INVALID-PTM-CONTEXT")
            )
        )
        fsm.act("INVALID-PTM-CONTEXT",
            If(self.ptm_trigger,
                NextState("ISSUE-PTM-REQUEST")
            )
        )
        fsm.act("ISSUE-PTM-REQUEST",
            req_ep.valid.eq(1),
            req_ep.request.eq(1),
            req_ep.response.eq(0),
            req_ep.first.eq(1),
            req_ep.last.eq(1),
            req_ep.length.eq(0),
            req_ep.requester_id.eq(pcie_endpoint.phy.id),
            req_ep.message_code.eq(PTM_REQUEST_MESSAGE_CODE),
            If(req_ep.ready,
                NextState("WAIT-PTM-RESPONSE")
            )
        )
        self.comb += ptm_sniffer.source.ready.eq(1)
        fsm.act("WAIT-PTM-RESPONSE",
            If(ptm_sniffer.source.valid,
                If(ptm_sniffer.source.master_time == 0, # FIXME: Add Response/ResponseD indication.
                    NextState("WAIT-1-US")
                ).Else(
                    self.ptm_update.eq(1),
                    NextValue(self.ptm_master_time,       ptm_sniffer.source.master_time),
                    NextValue(self.ptm_propagation_delay, ptm_sniffer.source.propagation_delay),
                    NextState("VALID-PTM-CONTEXT")
                )
            )
        )
        fsm.act("WAIT-1-US",
            self.req_timer.wait.eq(1),
            If(self.req_timer.done,
                NextState("ISSUE-PTM-REQUEST")
            )
        )
        fsm.act("VALID-PTM-CONTEXT",
            self.ptm_valid.eq(1),
            If(self.ptm_trigger,
                NextState("ISSUE-PTM-REQUEST")
            ),
            If(self.ptm_invalidation,
                NextState("INVALID-PTM-CONTEXT")
            ),
        )
