[> Run Unit-tests
-----------------
```sh
$ python3 -m unittest test.test_decoding
$ python3 -m unittest test.test_tlp_sniff
```

[> Build and test design
------------------------

```sh
$ ./ocp_tap_timecard.py --csr-csv=csr.csv --build --load
$ Reboot PC with TimeCard.
$ litex_server --jtag
$ litescope_cli -r analyzer_state
```
