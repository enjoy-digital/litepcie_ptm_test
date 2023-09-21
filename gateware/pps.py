#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *
from litex.gen.genlib.misc import WaitTimer

# PPS Generator ------------------------------------------------------------------------------------

class PPSGenerator(LiteXModule):
    def __init__(self, clk_freq, time, offset=int(500e6)):
        self.pps = Signal() # PPS Output.

        # # #

        # PPS Signals.
        start = Signal()
        count = Signal(32)

        # PPS FSM.
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(time != 0,
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            If(time > ((count * int(1e9) + offset)),
                start.eq(1),
                NextValue(count, count + 1)
            )
        )

        # PPS Generation.
        self.timer = WaitTimer(clk_freq*200e-3) # 20% High / 80% Low PPS.
        self.comb += self.timer.wait.eq(~start)
        self.comb += self.pps.eq(~self.timer.done)
