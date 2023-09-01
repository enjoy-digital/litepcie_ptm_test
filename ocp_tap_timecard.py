#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Build/Use ----------------------------------------------------------------------------------------
# Build/Load bitstream:
# ./ocp_tap_timecard.py --csr-csv=csr.csv --build --load
# ./ocp_tap_timecard.py --csr-csv=csr.csv --build --no-compile --driver
#
#.Build the kernel and load it:
# cd build/<platform>/driver/kernel
# make
# sudo ./init.sh
#
# Test userspace utilities:
# cd build/<platform>/driver/user
# make
# ./litepcie_util info
# ./litepcie_util scratch_test
# ./litepcie_util dma_test
# ./litepcie_util uart_test
#
# Debug over JTAGBone:
# litex_server --jtag --jtag-config=openocd_xc7_ft232.cfg
# litex_cli --regs
# litescope_cli

import os

from migen import *

from litex.gen import *

import ocp_tap_timecard_platform as ocp_tap_timecard

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litex.soc.cores.clock import *
from litex.soc.cores.led import LedChaser
from litex.soc.cores.xadc import XADC
from litex.soc.cores.dna  import DNA

from litedram.modules import MT41K256M16
from litedram.phy import s7ddrphy

from s7pciephy import S7PCIEPHY
from litepcie.software import generate_litepcie_software

from litescope import LiteScopeAnalyzer

# CRG ----------------------------------------------------------------------------------------------

class CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        #self.rst          = Signal()
        self.cd_sys       = ClockDomain()

        # Clk/Rst
        clk200 = platform.request("clk200")

        # PLL
        self.pll = pll = S7PLL()
        #self.comb += pll.reset.eq(self.rst)
        pll.register_clkin(clk200, 200e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin) # Ignore sys_clk to pll.clkin path created by SoC's rst.

# BaseSoC -----------------------------------------------------------------------------------------

class BaseSoC(SoCMini):
    SoCMini.csr_map = {
        "pcie_msi":       3, # Requires fixed mapping for MSI-X.
        "pcie_msi_table": 4, # Requires fixed mapping for MSI-X.
    }
    def __init__(self, sys_clk_freq=100e6, pcie_address_width=32, pcie_msi_type="msi-x", with_ptm=True,
        with_jtagbone           = True,
        with_led_chaser         = True,
        with_msi_analyzer       = False,
        with_ptm_conf_analyzer  = False,
        with_ptm_tlp_analyzer   = False,
        with_pcie_gtp_analyzer  = True,
        **kwargs):
        platform = ocp_tap_timecard.Platform()

        # CRG --------------------------------------------------------------------------------------
        self.crg = CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, sys_clk_freq,
            ident         = "LiteX SoC on OCP-TAP TimeCard",
            ident_version = True,
        )

        # JTAGBone ---------------------------------------------------------------------------------
        if with_jtagbone:
            self.add_jtagbone()
            platform.add_period_constraint(self.jtagbone_phy.cd_jtag.clk, 1e9/20e6)
            platform.add_false_path_constraints(self.jtagbone_phy.cd_jtag.clk, self.crg.cd_sys.clk)

        # XADC -------------------------------------------------------------------------------------
        self.xadc = XADC()

        # DNA --------------------------------------------------------------------------------------
        self.dna = DNA()
        self.dna.add_timing_constraints(platform, sys_clk_freq, self.crg.cd_sys.clk)

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq
            )

        # PCIe -------------------------------------------------------------------------------------
        self.pcie_phy = S7PCIEPHY(platform, platform.request("pcie_x1"),
            data_width = 64,
            bar0_size  = 0x10_0000, # 1MB.
            msi_type   = pcie_msi_type,
            with_ptm   = with_ptm,
        )
        self.add_pcie(phy=self.pcie_phy, ndmas=1, address_width=pcie_address_width, msi_type=pcie_msi_type, with_ptm=with_ptm)
        # FIXME: Apply it to all targets (integrate it in LitePCIe?).
        platform.add_period_constraint(self.crg.cd_sys.clk, 1e9/sys_clk_freq)
        platform.toolchain.pre_placement_commands.append("read_xdc /home/florent/dev/meta/litepcie_ptm/gateware/pcie/ip/pcie_s7/source/pcie_s7-PCIE_X0Y0.xdc")
        platform.toolchain.pre_placement_commands.append("read_xdc /home/florent/dev/meta/litepcie_ptm/gateware/pcie/ip/pcie_s7/synth/pcie_s7_ooc.xdc")
        platform.toolchain.pre_placement_commands.append("reset_property LOC [get_cells -hierarchical -filter {{NAME=~*gtp_channel.gtpe2_channel_i}}]")
        platform.toolchain.pre_placement_commands.append("set_property LOC GTPE2_CHANNEL_X0Y5 [get_cells -hierarchical -filter {{NAME=~*gtp_channel.gtpe2_channel_i}}]")

        # PCIe <-> Sys-Clk false paths.
        false_paths = [
            ("s7pciephy_clkout0", "sys_clk"),
            ("s7pciephy_clkout1", "sys_clk"),
            ("s7pciephy_clkout3", "sys_clk"),
        ]
        for clk0, clk1 in false_paths:
            platform.toolchain.pre_placement_commands.append(f"set_false_path -from [get_clocks {clk0}] -to [get_clocks {clk1}]")
            platform.toolchain.pre_placement_commands.append(f"set_false_path -from [get_clocks {clk1}] -to [get_clocks {clk0}]")

        # PTM capabilities -------------------------------------------------------------------------

        from ptm import PTMCapabilities

        self.ptm_capabilities = PTMCapabilities(self.pcie_endpoint)

        # PTM --------------------------------------------------------------------------------------

        from ptm import PTMCore

        self.ptm_core = PTMCore(self.pcie_endpoint, sys_clk_freq)
        self.comb += self.ptm_core.ptm_enable.eq(self.ptm_capabilities.ptm_enable)

        # Analyzer ---------------------------------------------------------------------------------

        if with_msi_analyzer:
            analyzer_signals = [
                self.pcie_msi.irqs,
                self.pcie_msi.port.source.valid,
                self.pcie_msi.table_port.adr,
                self.pcie_msi.table_port.dat_r,
                self.pcie_phy.sink,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 512,
                register     = True,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )

        if with_ptm_conf_analyzer:
            analyzer_signals = [
                self.ptm_capabilities.conf_ep,
                self.ptm_capabilities.comp_ep,

            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 512,
                register     = True,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )

        if with_ptm_tlp_analyzer:
            data_last   = Signal(64)
            data_change = Signal()
            self.sync += data_last.eq(self.pcie_phy.source.dat)
            self.sync += data_change.eq(self.pcie_phy.source.dat != data_last)
            analyzer_signals = [
                self.ptm_capabilities.ptm_enable,
                self.ptm_capabilities.ptm_root_select,
                self.ptm_capabilities.ptm_effective_granularity,
                self.ptm_core.req_timer.done,
                self.ptm_core.fsm,
                self.pcie_phy.source,
                self.pcie_phy.sink,
                self.pcie_phy.cfg_msg_received,
                data_change,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 512,
                register     = True,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )

        if with_pcie_gtp_analyzer:
            # PCIe Signals to observe.
            tx_ctrl = Signal(4)
            tx_data = Signal(4)
            rx_ctrl = Signal(4)
            rx_data = Signal(4)
            # Dummy logic to prevent synthesis optimizations.
            self.sync +=  [
                tx_ctrl.eq(tx_ctrl + 1),
                tx_data.eq(tx_data + 1),
                rx_ctrl.eq(rx_ctrl + 1),
                rx_data.eq(rx_data + 1),
            ]
            # Analyzer
            analyzer_signals = [
                tx_ctrl,
                tx_data,
                rx_ctrl,
                rx_data,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 1024,
                register     = True,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )
            # Magic .tcl commands to connect internals PCIe signals to LiteScope.
            # TODO.
            #platform.toolchain.pre_placement_commands.append("disconnect_net ...")
            #platform.toolchain.pre_placement_commands.append("connect_net ...")

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=ocp_tap_timecard.Platform, description="LiteX SoC on OCP-TAP TimeCard.")
    parser.add_target_argument("--flash",        action="store_true",       help="Flash bitstream.")
    parser.add_target_argument("--sys-clk-freq", default=100e6, type=float, help="System clock frequency.")
    parser.add_target_argument("--driver",       action="store_true", help="Generate PCIe driver.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        **parser.soc_argdict
    )

    builder  = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.driver:
        generate_litepcie_software(soc, os.path.join(builder.output_dir, "driver"))

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    if args.flash:
        prog = soc.platform.create_programmer()
        prog.flash(0, builder.get_bitstream_filename(mode="flash"))

if __name__ == "__main__":
    main()
