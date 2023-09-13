#!/usr/bin/env python3

import time
import argparse

from litex import RemoteClient

# Test ---------------------------------------------------------------------------------------------

def test_ptm(enable=1, loops=16):
    # Create Bus.
    bus = RemoteClient()
    bus.open()

    # Parameters.
    loop = 0

    # Configure PTM Requester.
    bus.regs.ptm_requester_control.write(enable)

    # Read Master Time received by PTM Requester.
    while loop < loops:
        r =  f"time   (s): {bus.regs.ptm_requester_master_time.read()/1e9:3.2f} "
        r += f"delay (ns): {bus.regs.ptm_requester_link_delay.read():d}"
        print(r)
        loop += 1
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
