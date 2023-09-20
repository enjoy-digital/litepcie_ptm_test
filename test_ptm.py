#!/usr/bin/env python3

import time
import argparse

from litex import RemoteClient

# Constants ----------------------------------------------------------------------------------------

PTM_CONTROL_ENABLE  = (1 << 0)
PTM_CONTROL_TRIGGER = (1 << 1)
PTM_STATUS_VALID    = (1 << 0)
PTM_STATUS_BUSY     = (1 << 1)

# Test ---------------------------------------------------------------------------------------------

def test_ptm(enable=1, loops=16):
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
        r =  f"valid : {bus.regs.ptm_requester_status.read() & PTM_STATUS_VALID} "
        r += f"master_time  (s): {bus.regs.ptm_requester_master_time.read()/1e9:3.2f} "
        r += f"link_delay  (ns): {bus.regs.ptm_requester_link_delay.read():d} "
        r += f"t1_time     (s): {bus.regs.ptm_requester_t1_time.read()/1e9:3.2f} "
        r += f"t4_time     (s): {bus.regs.ptm_requester_t4_time.read()/1e9:3.2f} "
        print(r)
        loop += 1
        bus.regs.ptm_requester_control.write(enable * PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER)
        while (bus.regs.ptm_requester_status.read() & PTM_STATUS_BUSY):
            pass
        time.sleep(1)

    # Close Bus.
    bus.close()

# Run ----------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", default=1, type=int, help="PTM Enable.")
    parser.add_argument("--loops",  default=8, type=int, help="Test Loops.")
    args = parser.parse_args()

    test_ptm(enable=args.enable, loops=args.loops)

if __name__ == "__main__":
    main()
