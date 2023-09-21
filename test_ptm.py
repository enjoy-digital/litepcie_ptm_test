#!/usr/bin/env python3

import time
import vcd
import argparse

from litex import RemoteClient

# Constants ----------------------------------------------------------------------------------------

PTM_CONTROL_ENABLE  = (1 << 0)
PTM_CONTROL_TRIGGER = (1 << 1)
PTM_STATUS_VALID    = (1 << 0)
PTM_STATUS_BUSY     = (1 << 1)

# Helper -------------------------------------------------------------------------------------------

def s_ns_to_ns(value):
    r  = ((value >> 32) & 0xffffffff) * int(1e9)
    r |= ((value >>  0) & 0xffffffff)
    return r

# Test ---------------------------------------------------------------------------------------------

def test_ptm(enable=1, loops=16, delay=1e-1, vcd_filename="test_ptm.vcd"):
    # Create Bus.
    bus = RemoteClient()
    bus.open()

    # Parameters.
    loop = 0

    # Configure PTM Requester and initiate 2 Requests.
    bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
    bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
    while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
        pass

    # VCD Writer.
    vcd_writer = vcd.VCDWriter(open(vcd_filename, "w"), timescale="1 ns", date="today")
    vcd_vars = {}
    vcd_vars["t1"]    = vcd_writer.register_var("module", "t1",    "wire", size=64)
    vcd_vars["t2"]    = vcd_writer.register_var("module", "t2",    "wire", size=64)
    vcd_vars["t3"]    = vcd_writer.register_var("module", "t3",    "wire", size=64)
    vcd_vars["t4"]    = vcd_writer.register_var("module", "t4",    "wire", size=64)
    vcd_vars["t2-t1"] = vcd_writer.register_var("module", "t2-t1", "wire", size=64)
    vcd_vars["t4-t1"] = vcd_writer.register_var("module", "t4-t1", "wire", size=64)
    vcd_vars["t2-diff"] = vcd_writer.register_var("module", "t2-diff", "wire", size=64)
    vcd_vars["t1-diff"] = vcd_writer.register_var("module", "t1-diff", "wire", size=64)
    # Read Master Time received by PTM Requester.
    t_start    = time.time()
    t2_ns_last = 0
    t1_ns_last = 0
    while loop < loops:
        # Loop Delay.
        while time.time() < (t_start + loop*delay):
            pass

        # Latch FPGA registers.
        valid          = bus.regs.ptm_requester_status.read() & PTM_STATUS_VALID
        master_time_ns = bus.regs.ptm_requester_master_time.read()
        link_delay_ns  = bus.regs.ptm_requester_link_delay.read()
        t2_ns = master_time_ns
        t3_ns = master_time_ns + link_delay_ns
        t1_ns = s_ns_to_ns(bus.regs.ptm_requester_t1_time.read())
        t4_ns = s_ns_to_ns(bus.regs.ptm_requester_t4_time.read())
        t_current = time.time()
        if loop > 1:
            vcd_writer.change(vcd_vars["t1"],    (t_current - t_start)*1e9, t1_ns)
            vcd_writer.change(vcd_vars["t2"],    (t_current - t_start)*1e9, t2_ns)
            vcd_writer.change(vcd_vars["t3"],    (t_current - t_start)*1e9, t3_ns)
            vcd_writer.change(vcd_vars["t4"],    (t_current - t_start)*1e9, t4_ns)
            vcd_writer.change(vcd_vars["t2-t1"], (t_current - t_start)*1e9, abs(t2_ns - t1_ns))
            vcd_writer.change(vcd_vars["t4-t1"], (t_current - t_start)*1e9, abs(t4_ns - t1_ns))
            vcd_writer.change(vcd_vars["t2-diff"], (t_current - t_start)*1e9, abs(t2_ns - t2_ns_last))
            vcd_writer.change(vcd_vars["t1-diff"], (t_current - t_start)*1e9, abs(t1_ns - t1_ns_last))
        r =  f"valid : {valid} "
        r += f"t2    (s): {t2_ns/1e9:.9f} "
        r += f"t3    (s): {t3_ns/1e9:.9f} "
        r += f"t1    (s): {t1_ns/1e9:.9f} "
        r += f"t4    (s): {t4_ns/1e9:.9f} "
        r += f"t2-t1 (s): {(t2_ns - t1_ns)/1e9:.9f} "
        r += f"t4-t1 (s): {(t4_ns - t1_ns)/1e9:.9f} "
        r += f"t2_ns-t2ns_last (s): {(t2_ns - t2_ns_last)/1e9:.9f} "
        r += f"t1_ns-t1ns_last (s): {(t1_ns - t1_ns_last)/1e9:.9f} "
        print(r)
        # Increment Loop.
        loop += 1
        # Initiate/Wait PTM Request.
        bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
        while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
            pass
        t2_ns_last = t2_ns
        t1_ns_last = t1_ns

    # Close Bus.
    bus.close()


def test_ptm_tX(enable=1, loops=16, delay=1e-1, tX="t2",vcd_filename="test_ptm.vcd"):
    # Create Bus.
    bus = RemoteClient()
    bus.open()

    # Parameters.
    loop = 0

    # Configure PTM Requester and initiate 2 Requests.
    bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
    bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
    while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
        pass

    # VCD Writer.
    vcd_writer = vcd.VCDWriter(open(vcd_filename, "w"), timescale="1 ns", date="today")
    vcd_vars = {}
    vcd_vars["t"]         = vcd_writer.register_var("module", "t",        "real", size=64)
    vcd_vars["t-diff"]    = vcd_writer.register_var("module", "t-diff",   "real", size=64)
    vcd_vars["tX"]        = vcd_writer.register_var("module", "tX",        "real", size=64)
    vcd_vars["tX-diff"]   = vcd_writer.register_var("module", "tX-diff",   "real", size=64)
    vcd_vars["tX-t-diff"] = vcd_writer.register_var("module", "tX-t-diff", "real", size=64)
    # Read Master Time received by PTM Requester.
    t_start    = time.time()
    t_ns_last  = 0
    tX_ns_last = 0
    while loop < loops:
        # Loop Delay.
        while time.time() < (t_start + loop*delay):
            pass
        t_current  = (time.time() - t_start)
        # Latch FPGA registers.
        if tX == "t2":
            tX_ns = bus.regs.ptm_requester_master_time.read()
        if tX == "t1":
            #tX_ns = s_ns_to_ns(bus.regs.ptm_requester_t1_time.read())
            tX_ns = bus.regs.ptm_requester_t1_time.read()
        t_ns       = t_current*1e9
        t_ns_diff  = (t_ns  - t_ns_last)
        tX_ns_diff = (tX_ns - tX_ns_last)
        if loop > 1:
            vcd_writer.change(vcd_vars["t"],         t_ns, t_ns)
            vcd_writer.change(vcd_vars["t-diff"],    t_ns, t_ns_diff)
            vcd_writer.change(vcd_vars["tX"],        t_ns, tX_ns)
            vcd_writer.change(vcd_vars["tX-diff"],   t_ns, tX_ns_diff)
            vcd_writer.change(vcd_vars["tX-t-diff"], t_ns, t_ns_diff - tX_ns_diff)
        r  = f"t (s): {t_ns/1e9:.9f} "
        r += f"t_ns-tns_last (s): {(t_ns - t_ns_last)/1e9:.9f} "
        r += f"tX (s): {tX_ns/1e9:.9f} "
        r += f"tX_ns-tXns_last (s): {(tX_ns - tX_ns_last)/1e9:.9f} "
        #print(r)
        # Increment Loop.
        loop += 1
        # Initiate/Wait PTM Request.
        bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
        t_ns_last  = t_ns
        tX_ns_last = tX_ns


    # Close Bus.
    bus.close()

# Run ----------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", default=1,    type=int,   help="PTM Enable.")
    parser.add_argument("--loops",  default=100,  type=int,   help="Test Loops.")
    parser.add_argument("--delay",  default=1e-1, type=float, help="Loop delay.")
    parser.add_argument("--vcd",    default="test_ptm.vcd",   help="VCD dump file")
    args = parser.parse_args()

    #test_ptm(enable=args.enable, loops=args.loops, delay=args.delay, vcd_filename=args.vcd)
    #test_ptm_tX(enable=args.enable, loops=args.loops, delay=args.delay, tX="t2", vcd_filename=args.vcd)
    test_ptm_tX(enable=args.enable, loops=args.loops, delay=args.delay, tX="t1", vcd_filename=args.vcd)

if __name__ == "__main__":
    main()
