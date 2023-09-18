#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

# Time Generator -----------------------------------------------------------------------------------

class TimeGenerator(LiteXModule):
    def __init__(self, clk_domain, clk_freq):
        assert 1e9/clk_freq == int(1e9/clk_freq)
        self.time = time = Signal(64)

        # # #

        self.cd_time = ClockDomain()
        self.comb += [
            self.cd_time.clk.eq(ClockSignal(clk_domain)),
            self.cd_time.rst.eq(ClockSignal(clk_domain)),
        ]
        self.sync.time += time.eq(time + int(1e9/clk_freq))
