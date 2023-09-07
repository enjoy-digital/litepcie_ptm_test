#!/usr/bin/env python3

import time

from litex import RemoteClient

bus = RemoteClient()
bus.open()

# # #

master_time_current = 0
master_time_last    = 0
master_time_diff    = 0
while True:
    master_time_current = bus.regs.main_ptm_master_time.read()
    master_time_diff    = master_time_current - master_time_last
    print(master_time_diff/1e9)
    time.sleep(1)
    master_time_last = master_time_current

# # #

bus.close()