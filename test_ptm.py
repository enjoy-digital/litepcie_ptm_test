#!/usr/bin/env python3

import time
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

def test_ptm(enable=1, loops=16, delay=1e-1):
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

    # Read Master Time received by PTM Requester.
    while loop < loops:
        # Latch FPGA registers.
        valid          = bus.regs.ptm_requester_status.read() & PTM_STATUS_VALID
        master_time_ns = bus.regs.ptm_requester_master_time.read()
        link_delay_ns  = bus.regs.ptm_requester_link_delay.read()
        t1_time_ns     = s_ns_to_ns(bus.regs.ptm_requester_t1_time.read())
        t4_time_ns     = s_ns_to_ns(bus.regs.ptm_requester_t4_time.read())
        r =  f"valid : {valid} "
        r += f"master_time  (s): {master_time_ns/1e9:3.2f} "
        r += f"link_delay  (ns): {link_delay_ns:d} "
        r += f"t1_time      (s): {t1_time_ns/1e9:3.2f} "
        r += f"t4_time      (s): {t4_time_ns/1e9:3.2f} "
        print(r)
        # Increment Loop.
        loop += 1
        # Initiate/Wait PTM Request.
        bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
        while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
            pass
        # Loop Delay.
        time.sleep(delay)

    # Close Bus.
    bus.close()

# Run ----------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", default=1,    type=int,   help="PTM Enable.")
    parser.add_argument("--loops",  default=8,    type=int,   help="Test Loops.")
    parser.add_argument("--delay",  default=1e-0, type=float, help="Loop delay.")
    args = parser.parse_args()

    test_ptm(enable=args.enable, loops=args.loops, delay=args.delay)

if __name__ == "__main__":
    main()
