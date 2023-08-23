#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause


from migen import *

from litex.gen import *

# PTM Capabilities ---------------------------------------------------------------------------------

class PTMCapabilities(LiteXModule):
    def __init__(self, pcie_endpoint):
        self.conf_source = conf_source = pcie_endpoint.depacketizer.conf_source

        self.ptm_conf_fsm = ptm_conf_fsm = FSM(reset_state="IDLE")

        mem = Memory(32, 3, init=[
            0x0001_001f, # 0x00 : PTM Extended Capbility Header.
            0x0000_1003, # 0x04 : PTM Capability Register: Requester/Responder capable / 16ns.
            0x0000_0000, # 0x08 : PTM Control Register.
        ])
        mem_wr_port = mem.get_port(write_capable=True)
        mem_rd_port = mem.get_port(async_read=True)
        self.specials += mem, mem_wr_port, mem_rd_port

        reg = Signal(10)
        dat = Signal(32)

        ptm_conf_fsm.act("IDLE",
            If(conf_source.valid,
                If(conf_source.we,
                    NextState("WRITE-MEM")
                ).Else(
                    NextState("READ-MEM")
                )
            )
        )
        self.comb += reg.eq((Cat(conf_source.register_no, conf_source.ext_reg) - 0x6B))
        ptm_conf_fsm.act("WRITE-MEM",
            conf_source.ready.eq(1),
            mem_wr_port.adr.eq(reg),
            mem_wr_port.we.eq(1),
            mem_wr_port.dat_w.eq(conf_source.dat),
            NextState("IDLE")
        )
        ptm_conf_fsm.act("READ-MEM",
            mem_rd_port.adr.eq(reg),
            NextValue(dat, mem_rd_port.dat_r),
            NextState("SEND-COMPLETION")
        )
        self.comp_port = comp_port = pcie_endpoint.crossbar.get_slave_port(address_decoder=lambda a: 0)
        ptm_conf_fsm.act("SEND-COMPLETION",
            comp_port.source.valid.eq(1),
            comp_port.source.first.eq(1),
            comp_port.source.last.eq(1),
            comp_port.source.len.eq(1),
            comp_port.source.err.eq(0),
            comp_port.source.tag.eq(conf_source.tag),
            comp_port.source.adr.eq(0),
            comp_port.source.cmp_id.eq(pcie_endpoint.phy.id),
            comp_port.source.req_id.eq(conf_source.req_id),
            comp_port.source.dat.eq(dat),
            If(comp_port.source.valid & comp_port.source.ready,
                conf_source.ready.eq(1),
                NextState("IDLE")
            )
        )
