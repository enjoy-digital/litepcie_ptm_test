#
# This file is part of LitePCIe-PTM.
#
# Copyright (c) 2023 NetTimeLogic
# Copyright (c) 2019-2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

# Helpers ------------------------------------------------------------------------------------------

def K(x, y):
    """K code generator ex: K(28, 5) is COM Symbol"""
    return (y << 5) | x

def D(x, y):
    """D code generator"""
    return (y << 5) | x

# Symbols (6.3.5) ----------------------------------------------------------------------------------

class Symbol:
    """Symbol definition with name, 8-bit value and description"""
    def __init__(self, name, value, description=""):
        self.name        = name
        self.value       = value
        self.description = description

SKP =  Symbol("SKP", K(28, 1), "Skip")
SDP =  Symbol("SDP", K(28, 2), "Start Data Packet")
EDB =  Symbol("EDB", K(28, 3), "End Bad")
SUB =  Symbol("SUB", K(28, 4), "Decode Error Substitution")
COM =  Symbol("COM", K(28, 5), "Comma")
RSD =  Symbol("RSD", K(28, 6), "Reserved")
SHP =  Symbol("SHP", K(27, 7), "Start Header Packet")
END =  Symbol("END", K(29, 7), "End")
SLC =  Symbol("SLC", K(30, 7), "Start Link Command")
EPF =  Symbol("EPF", K(23, 7), "End Packet Framing")

symbols = [SKP, SDP, EDB, SUB, COM, RSD, SHP, END, SLC, EPF]

# Endianness Swap ----------------------------------------------------------------------------------

class EndiannessSwap(LiteXModule):
    """Swap the data bytes/ctrl bits of stream"""
    def __init__(self, sink, source):
        assert len(sink.data) == len(source.data)
        assert len(sink.ctrl) == len(source.ctrl)
        self.comb += sink.connect(source, omit={"data", "ctrl"})
        n = len(sink.ctrl)
        for i in range(n):
            self.comb += source.data[8*i:8*(i+1)].eq(sink.data[8*(n-1-i):8*(n-1-i+1)])
            self.comb += source.ctrl[i].eq(sink.ctrl[n-1-i])
