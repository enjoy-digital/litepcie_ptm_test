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

        self.enable           = Signal()
        self.override         = Signal()
        self.override_time_ns = Signal(32)
        self.override_time_s  = Signal(32)

        # # #

        # Time Signals.
        self.time_ns = time_ns = Signal(32)
        self.time_s  = time_s  = Signal(32)

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
                time_ns.eq(0),
                time_s.eq(0),
            # External Override.
            ).Elif(self.override,
                time_ns.eq(self.override_time_ns),
                time_s.eq(self.override_time_s),
            # Increment.
            ).Else(
                time_ns.eq(time_ns + int(1e9/clk_freq)),
                If(time_ns >= (int(1e9) - int(1e9/clk_freq)),
                    time_ns.eq(0),
                    time_s.eq(time_s + int(1e9/clk_freq))
                )
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
        self._time_ns = CSRStatus(32, description="Latched Time (32-bit ns part).")
        self._time_s  = CSRStatus(32, description="Latched Time (32-bit  s part).")
        self._override_time_ns = CSRStorage(32, description="Override Time (32-bit ns part).")
        self._override_time_s  = CSRStorage(32, description="Override Time (32-bit  s part).")

        # # #

        # Enable.
        self.specials += MultiReg(self._control.fields.enable, self.enable)

        # Time Sampling.
        time_latch_ns = Signal(32)
        time_latch_s  = Signal(32)
        time_latch_ps = PulseSynchronizer("sys", "time")
        self.submodules += time_latch_ps
        self.comb += time_latch_ps.i.eq(self._control.fields.latch)
        self.sync.time += If(time_latch_ps.o,
            time_latch_ns.eq(self.time_ns),
            time_latch_s.eq(self.time_s),
        )
        self.specials += MultiReg(time_latch_ns, self._time_ns.status)
        self.specials += MultiReg(time_latch_s,  self._time_s.status)

        # Time Override.
        self.specials += MultiReg(self._override_time_ns.storage, self.override_time_ns, "time")
        self.specials += MultiReg(self._override_time_s.storage,  self.override_time_s,  "time")
        time_override_ps = PulseSynchronizer("sys", "time")
        self.submodules += time_override_ps
        self.comb += time_override_ps.i.eq(self._control.fields.override)
        self.comb += self.override.eq(time_override_ps.o)
