#!/usr/bin/env python3

import time
import argparse

from litex import RemoteClient

# Constants ----------------------------------------------------------------------------------------

TIME_CONTROL_ENABLE = (1 << 0)
TIME_CONTROL_READ   = (1 << 1)
TIME_CONTROL_WRITE  = (1 << 2)

# Test Time ----------------------------------------------------------------------------------------

def test_time(enable=1, loops=16):
    # Create Bus.
    bus = RemoteClient()
    bus.open()

    # Parameters.
    loop = 0

    # Configure Time Controller.

    bus.regs.time_generator_control.write(enable * TIME_CONTROL_ENABLE | TIME_CONTROL_READ)

    # Read Time from Time Controller.
    print("Read Time from Time Controller...")
    loop = 0
    while loop < loops:
        r =   f"time (s): {bus.regs.time_generator_read_time.read()/1e9:0.9f} "
        print(r)
        loop += 1
        bus.regs.time_generator_control.write(enable * TIME_CONTROL_ENABLE | TIME_CONTROL_READ)
        time.sleep(1)


    # Override Time.
    print("Override Time to 100s...")
    bus.regs.time_generator_override_time.write(int(100*1e9))
    bus.regs.time_generator_control.write(enable * TIME_CONTROL_ENABLE | TIME_CONTROL_WRITE)
    bus.regs.time_generator_control.write(enable * TIME_CONTROL_ENABLE | TIME_CONTROL_READ)

    # Read Time from Time Controller.
    print("Read Time from Time Controller...")
    loop = 0
    while loop < loops:
        r =  f"time (s): {bus.regs.time_generator_time.read()/1e9:0.9f} "
        print(r)
        loop += 1
        bus.regs.time_generator_control.write(enable * TIME_CONTROL_ENABLE | TIME_CONTROL_READ)
        time.sleep(1)


    # Close Bus.
    bus.close()

# Run ----------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", default=1, type=int, help="PTM Enable.")
    parser.add_argument("--loops",  default=8, type=int, help="Test Loops.")
    args = parser.parse_args()

    test_time(enable=args.enable, loops=args.loops)

if __name__ == "__main__":
    main()
