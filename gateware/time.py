#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer

from litex.gen import *
from litex.soc.interconnect.csr import *

# Time Generator -----------------------------------------------------------------------------------

class TimeGenerator(LiteXModule):
    def __init__(self, clk_domain, clk_freq):
        assert 1e9/clk_freq == int(1e9/clk_freq)
        self.time = time = Signal(64)

        # # #

        # Time Clk Domain.
        self.cd_time = ClockDomain()
        self.comb += [
            self.cd_time.clk.eq(ClockSignal(clk_domain)),
            self.cd_time.rst.eq(ResetSignal(clk_domain)),
        ]

        # Time Increment.
        self.sync.time += time.eq(time + int(1e9/clk_freq))


# Time Controller ----------------------------------------------------------------------------------

class TimeController(LiteXModule):
    def __init__(self, clk_domain, clk_freq, with_csr=True):
        assert 1e9/clk_freq == int(1e9/clk_freq)

        self.enable        = Signal()
        self.override      = Signal()
        self.override_time = Signal(64)

        # # #

        # Time Signals.
        self.time = time = Signal(64)

        # Time Clk Domain.
        self.cd_time = ClockDomain()
        self.comb += [
            self.cd_time.clk.eq(ClockSignal(clk_domain)),
            self.cd_time.rst.eq(ResetSignal(clk_domain)),
        ]

        # Time Handling.
        self.sync.time += [
            # Disable: Reset Time to 0.
            If(~self.enable,
                time.eq(0),
            # External Override.
            ).Elif(self.override,
                time.eq(self.override_time),
            # Increment.
            ).Else(
                time.eq(time + int(1e9/clk_freq)),
            )
        ]

        # CSRs.
        if with_csr:
            self.add_csr(clk_domain)

    def add_csr(self, clk_domain, default_enable=1):
        self._control = CSRStorage(fields=[
            CSRField("enable", size=1, offset=0, values=[
                ("``0b0``", "Time Controller Disabled."),
                ("``0b1``", "Time Controller Enabled."),
            ], reset=default_enable),
            CSRField("latch",    size=1, offset=1, pulse=True),
            CSRField("override", size=1, offset=2, pulse=True),
        ])
        self._time          = CSRStatus(64,  description="Latched Time (ns).")
        self._override_time = CSRStorage(64, description="Override Time (ns).")

        # # #

        # Enable.
        self.specials += MultiReg(self._control.fields.enable, self.enable)

        # Time Sampling.
        time_latch = Signal(64)
        time_latch_ps = PulseSynchronizer("sys", "time")
        self.submodules += time_latch_ps
        self.comb += time_latch_ps.i.eq(self._control.fields.latch)
        self.sync.time += If(time_latch_ps.o, time_latch.eq(self.time))
        self.specials += MultiReg(time_latch, self._time.status)

        # Time Override.
        self.specials += MultiReg(self._override_time.storage, self.override_time, "time")
        time_override_ps = PulseSynchronizer("sys", "time")
        self.submodules += time_override_ps
        self.comb += time_override_ps.i.eq(self._control.fields.override)
        self.comb += self.override.eq(time_override_ps.o)
