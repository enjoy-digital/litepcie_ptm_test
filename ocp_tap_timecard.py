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
from litex.gen.genlib.misc import WaitTimer

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

from gateware.pcie.s7pciephy import S7PCIEPHY
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
        with_jtagbone                = True,
        with_led_chaser              = True,
        with_msi_analyzer            = False,
        with_ptm_conf_analyzer       = False,
        with_ptm_tlp_analyzer        = False,
        with_pcie_sniffer_analyzer   = False,
        with_pcie_requester_analyzer = False,
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

        from gateware.ptm import PTMCapabilities

        self.ptm_capabilities = PTMCapabilities(self.pcie_endpoint)

        # PTM --------------------------------------------------------------------------------------

        from gateware.ptm import PTMSniffer, PTMRequester

        # PTM Sniffer.
        self.ptm_sniffer = PTMSniffer(
            rx_rst_n = self.pcie_phy.sniffer_rst_n,
            rx_clk   = self.pcie_phy.sniffer_clk,
            rx_data  = self.pcie_phy.sniffer_rx_data,
            rx_ctrl  = self.pcie_phy.sniffer_rx_ctl,
        )

        # PTM Requester.
        self.ptm_requester = PTMRequester(
            pcie_endpoint = self.pcie_endpoint,
            ptm_sniffer   = self.ptm_sniffer,
            sys_clk_freq  = sys_clk_freq,
        )
        self.comb += self.ptm_requester.ptm_enable.eq(self.ptm_capabilities.ptm_enable)

        # PTM Trigger.
        self.ptm_trigger = WaitTimer(100e-3*sys_clk_freq)
        self.comb += self.ptm_trigger.wait.eq(~self.ptm_trigger.done)
        self.comb += self.ptm_requester.ptm_trigger.eq(self.ptm_trigger.done)

        counter = Signal(32)
        self.sync += counter.eq(counter + 1)
        sma0 = platform.request("sma", 0)
        self.comb += sma0.dat_in_en.eq(1)
        self.comb += sma0.dat_out_en.eq(0)
        self.comb += sma0.dat_out.eq(counter[10])

        sma1 = platform.request("sma", 1)
        self.comb += sma1.dat_in_en.eq(1)
        self.comb += sma1.dat_out_en.eq(0)
        self.comb += sma1.dat_out.eq(counter[10])

        sma2 = platform.request("sma", 2)
        self.comb += sma2.dat_in_en.eq(1)
        self.comb += sma2.dat_out_en.eq(0)
        self.comb += sma2.dat_out.eq(counter[10])

        sma3 = platform.request("sma", 3)
        self.comb += sma3.dat_in_en.eq(1)
        self.comb += sma3.dat_out_en.eq(0)
        self.comb += sma3.dat_out.eq(counter[10])

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

        if with_pcie_sniffer_analyzer:
            # Analyzer
            analyzer_signals = [
                self.ptm_requester.ptm_trigger,
                self.ptm_sniffer.source,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 2048,
                register     = True,
                samplerate   = 125e6,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )

        if with_pcie_requester_analyzer:
            # Analyzer
            analyzer_signals = [
                self.ptm_requester.ptm_enable,
                self.ptm_requester.ptm_trigger,
                self.ptm_requester.ptm_valid,
                self.ptm_requester.ptm_update,
                self.ptm_requester.ptm_master_time,
                self.ptm_requester.ptm_propagation_delay,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 256,
                register     = True,
                samplerate   = 125e6,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv"
            )

            self._ptm_valid             = CSRStatus()
            self._ptm_master_time       = CSRStatus(64)
            self._ptm_propagation_delay = CSRStatus(32)
            self.sync += [
                self._ptm_valid.status.eq(self.ptm_requester.ptm_valid),
                self._ptm_master_time.status.eq(self.ptm_requester.ptm_master_time),
                self._ptm_propagation_delay.status.eq(self.ptm_requester.ptm_propagation_delay),
            ]

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
