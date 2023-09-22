```
                   __   _ __      ___  _________        ___  ________  ___
                  / /  (_) /____ / _ \/ ___/  _/__ ____/ _ \/_  __/  |/  /
                 / /__/ / __/ -_) ___/ /___/ // -_)___/ ___/ / / / /|_/ /
                /____/_/\__/\__/_/   \___/___/\__/   /_/    /_/ /_/  /_/
                        LitePCIe PTM support / test repository.
                            Copyright (c) 2023 NetTimeLogic
                            Copyright (c) 2023 Enjoy-Digital
```

[> Intro
--------

The project provides PTM support/demo with LitePCIe on the TimeCard.

![](doc/timecard.png)

The FPGA board is configured as a PTM Requester and a utilities/tests are provided to demonstrate correct operation.

To ease integration/maintenance, the PTM packets definition and Packetizer/Depacketizer modules are directly integrated in [LitePCIe](https://github.com/enjoy-digital/litepcie). This project then provides:
- A PCIePTMSniffer module sniffing GTPE2 <-> PCIE2 traffic and generating PTM Responses (Could be optional with other PCIe PHYs allowing PTM TLP messages).
- A TimeGenerator module to generate local time and interfacing with the Linux driver.
- A PPSGenerator module to generate a PPS and allow external synchronization comparison with another PTM compatible board.
- A LiteX design example integrating LitePCIe with PTM support enabled and the demo application.
- A Linux driver adding PTP/PTM support to LitePCIe driver.


As a demonstration of the work, a demo application has been prepared to synchronize the time of an Intel I225 Network Card to the time of the TimeCard through PTM/Linux/PHC2Sys utility with both boards generating a PPS and a logic analyzer capturing both PPS to check synchronization:

![](doc/ptm_setup.png)

[> Prerequisites / System setup
-------------------------------
These are required in order to build and use the FPGA design and associated software provided in this project:
- Linux computer, PTM capable (Tested with Ubuntu 20.04).
- Python3, Xilinx Vivado installed.
- LiteX [installed](https://github.com/enjoy-digital/litex/wiki/Installation#litex-installation-guide) and up to date (2023.09.22).
- An OCP-Tap TimeCard.
- An Intel I225 board.
- A JTAG-HS2 Cable.
- A Logic Analyzer/Scope to observe PPS.

[> Xilinx PHY workaround / Implementation note
----------------------------------------------

From our understanding of the Xilinx PHY and [question](https://support.xilinx.com/s/question/0D54U00007HkzneSAB/receive-all-message-tlps-on-user-interface-7-series-fpga-integrated-block?language=en_US) asked on Xilinx community forum, the Artix7's Xilinx PHY does not allow redirecting PTM TLP messages to the AXI interface. For a PTM Requester, this then prevent receiving the PTM Response/ResponseD TLP messages.

To work-around this limitation, a PCIePTMSniffer has been implemented: The module is sniffing the RX Data between the GTPE2 and PCIE2 hardblocks and descrambling/decoding the PCIe traffic to re-generate the PTM TLPs.

The re-generated PTM TLPs can then be re-injected in to LitePCIe core and use its PTM Depacketizer:

![](doc/ptm_sniffer.png)

[> Run Unit-tests
-----------------

Implementing the PCIePTMSniffer module required doing some hardware capture with Litescope of the GTPE2 <-> PCIE2 hardblock traffic. These raw captures have been used to create descrambling/decoding logic and can be found in test directory.

These tests can be exectuted with:
```sh
$ python3 -m unittest test.test_raw_sniffer
$ python3 -m unittest test.test_tlp_sniffer
```

[> Build and test design
------------------------
The FPGA design can be build and tested with the following commands:

```sh
$ ./ocp_tap_timecard.py --csr-csv=csr.csv --build --load
$ Reboot the remote PC with the TimeCard.
$ litex_server --jtag
$ litescope_cli (for LiteScope use when design is built with a LiteScope analyzer probe)
$ ./test_time.py
$ ./test_ptm.py
```

[> Run PHC2SYS / PPS Demo
-------------------------

A demo application has been prepared, allowing time synchronization of an Intel I225 Network Card to the time of the TimeCard through PTM/Linux/phc2sys , with both boards generating a PPS and a logic analyzer capturing both PPS to check synchronization:

Start **TimeCard's time -> Host's CLOCK_REALTIME** regulation:
```sh
$ cd kernel
$ make clean all
$ sudo ./init.sh
$ sudo systemctl stop systemd-timesyncd.service
$ sudo phc_ctl /dev/ptp2 set
$ sudo phc2sys -c CLOCK_REALTIME -s /dev/ptp2 -O 0 -N1 -m
```

Start **Host's CLOCK_REALTIME -> Intel I225's time** regulation:
```sh
$ sudo /bin/bash
$ echo 1 > /sys/class/ptp/ptp0/pps_enable
$ echo 2 0 > /sys/class/ptp/ptp0/pins/SDP0
$ echo '0 0 0 1 0' > /sys/class/ptp/ptp0/period
$ sudo phc2sys -s CLOCK_REALTIME -c /dev/ptp0 -O 0 -m
```

Correct regulation/alignement of the two PPS can be observed with a logic analyzer:

![](doc/ptm_demo_pps_alignment.png)

PPS edges have also been observed with a scope to evaluate aligment offset/jitter:

![](doc/ptm_demo_pps_jitter.png)

Regulation with phc2sys introduces most of the jitter, which could probably be reduced by fine tuning
phc2sys's rate/KP/KI parameters.

An offset is also present and could be reduced to a minimal value by taking into account all hardware
delays in the regulation chain:
- Time resynchronization delay between TimeGenerator and PTMRequester.
- PPSGenerator delay between TimeGenerator and PPSGenerator.
- PCIe PHY logic TX/RX delays.

Since TimeGenerator and PPSGenerator modules are minimalist and created just for this demo application, it will
be more interesting to fine tune the offset/delays on the final application. The work done here and
the demo should provide a good basis for this.

Inserting a glitch in the regulation and observe correct re-alignement can be done by simply changing
the date of the system:

```sh
$ Ctrl-C on TimeCard phc2sys
$ sudo date -s XX:YY (a few seconds in the future)
$ sudo phc2sys -c CLOCK_REALTIME -s /dev/ptp2 -O 0 -N1 -m
```