#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Build/Use ----------------------------------------------------------------------------------------
# Build/Load bitstream:
# ./ocp_tap_timecard.py --csr-csv=csr.csv --build --load

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
    def __init__(self, sys_clk_freq=100e6, with_jtagbone=True, **kwargs):
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

        self.leds = LedChaser(
            pads         = platform.request_all("user_led"),
            sys_clk_freq = sys_clk_freq
        )

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


# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=ocp_tap_timecard.Platform, description="LiteX SoC on OCP-TAP TimeCard.")
    parser.add_target_argument("--flash",        action="store_true",       help="Flash bitstream.")
    parser.add_target_argument("--sys-clk-freq", default=100e6, type=float, help="System clock frequency.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        **parser.soc_argdict
    )

    builder  = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    if args.flash:
        prog = soc.platform.create_programmer()
        prog.flash(0, builder.get_bitstream_filename(mode="flash"))

if __name__ == "__main__":
    main()
