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

# Test ---------------------------------------------------------------------------------------------

def test_ptm(enable=1, loops=16, delay=1e-1, vcd_filename="test_ptm.vcd"):
    # Create Bus.
    bus = RemoteClient()
    bus.open()

    # Parameters.
    loop = 0

    # Initiate PTM Request and Wait for Response.
    bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
    while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
        pass

    # VCD Writer.
    vcd_writer = vcd.VCDWriter(open(vcd_filename, "w"), timescale="1 ns", date="today")
    vcd_vars = {}
    vcd_vars["t1"]    = vcd_writer.register_var("module", "t1",    "real", size=64)
    vcd_vars["t2"]    = vcd_writer.register_var("module", "t2",    "real", size=64)
    vcd_vars["t3"]    = vcd_writer.register_var("module", "t3",    "real", size=64)
    vcd_vars["t4"]    = vcd_writer.register_var("module", "t4",    "real", size=64)
    vcd_vars["t2-t1"] = vcd_writer.register_var("module", "t2-t1", "real", size=64)
    vcd_vars["t4-t1"] = vcd_writer.register_var("module", "t4-t1", "real", size=64)
    # Read Master Time received by PTM Requester.
    t_start = time.time()
    while loop < loops:
        # Time.
        t_s  = (time.time() - t_start)
        t_ns = t_s*1e9

        # Loop Delay.
        if t_s < (loop*delay):
            continue

        # Initiate PTM Request and Wait for Response.
        bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
        while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
            pass

        # Latch FPGA registers.
        valid          = bus.regs.ptm_requester_status.read() & PTM_STATUS_VALID
        master_time_ns = bus.regs.ptm_requester_master_time.read()
        link_delay_ns  = bus.regs.ptm_requester_link_delay.read()
        t2_ns = master_time_ns
        t3_ns = master_time_ns + link_delay_ns
        t1_ns = bus.regs.ptm_requester_t1_time.read()
        t4_ns = bus.regs.ptm_requester_t4_time.read()
        if loop > 0:
            vcd_writer.change(vcd_vars["t1"],    t_ns, t1_ns)
            vcd_writer.change(vcd_vars["t2"],    t_ns, t2_ns)
            vcd_writer.change(vcd_vars["t3"],    t_ns, t3_ns)
            vcd_writer.change(vcd_vars["t4"],    t_ns, t4_ns)
            vcd_writer.change(vcd_vars["t2-t1"], t_ns, t2_ns - t1_ns)
            vcd_writer.change(vcd_vars["t4-t1"], t_ns, t4_ns - t1_ns)
        r =  f"valid : {valid} "
        r += f"t2    (s): {t2_ns/1e9:.9f} "
        r += f"t3    (s): {t3_ns/1e9:.9f} "
        r += f"t1    (s): {t1_ns/1e9:.9f} "
        r += f"t4    (s): {t4_ns/1e9:.9f} "
        r += f"t2-t1 (s): {(t2_ns - t1_ns)/1e9:.9f} "
        r += f"t4-t1 (s): {(t4_ns - t1_ns)/1e9:.9f} "
        print(r)

        # Increment Loop.
        loop += 1

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

    test_ptm(enable=args.enable, loops=args.loops, delay=args.delay, vcd_filename=args.vcd)

if __name__ == "__main__":
    main()
