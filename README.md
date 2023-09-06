[> Run Unit-tests
-----------------
```sh
$ python3 -m unittest test.test_raw_sniffer
$ python3 -m unittest test.test_tlp_sniffer
```

[> Build and test design
------------------------

```sh
$ ./ocp_tap_timecard.py --csr-csv=csr.csv --build --load
$ Reboot PC with TimeCard.
$ litex_server --jtag
$ litescope_cli -r analyzer_state
```
