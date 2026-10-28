     :+#@@@@@@##:                                                          ::
   :#@@@@###@@@@@@+                                                    ++#+::
  :@@#:       +@@@@+                                                   +@:+#+#+::  :+@@@@#
  @@+  :@@@@:  #@@@# +@@@@@@:  :@@@@@  #@@@@+                    ~~~  :++#@###+::::++@@@@#
  @@   @@@@#  :@@@@  @@@@@@@+  +@@@@@ :@@@@@:             ~~~~ ~~~~~~++  #@+  :+@:::+@@@@#~
  :@  +@@@@##@@@#+  @@@@:@@@#  #@@@@@+@@@@@@            :~~~:::::++#++###@@:###+#+   +##@#  ~~~~
    : @@@@#+@@@@@: +@@@+:@@@#  @@@@@@@@@@@@@      ::::@@+ :+#+::::+#+:::+++:::++##+::  +##~~~~ ~~~
     #@@@@  +@@@@  @@@@@@@@@@ :@@@+#@@#+@@@+     ~@@@@+  +#@@@#@+ ##++##:#@######@@@@ :@#++~~~
    :@@@@:  @@@@+ @@@@+++@@@@ +@@@+#@@##@@@:    ~#@##::+##+###@@@ ++:#:@@+@@@@@@@@@@@+ ++++~~~~
    :::::   ::::  ::::   :::::   :::::        :##+::##+:+#:+#@@@#:++@++##@@@@####@@@@+:++~~~
                              #@@@@@@@@@@@@:
                            +@@@#:    :#@@@@+
        ~~: :+++:   ##:    :@@+  :++++  +@@@@  :+:::::     :++++::  +++  ::::  :+++    :+++++:
      ~~~:#@@##@@@#+#@@+   #@+  :@@@@+  +@@@@ :@@@@@@@   #@@@@@@@# #@@@: @@@@# #@@@  +@@@@@@@@:
     ~~~+@@#+: :@@@@@@@@:  :@:  #@@@@ :#@@@#  @@@@@@@@  #@@@@@@@@: @@@@ :@@@@@+@@@# +@@@@#####
     ~~~#@:@@@:@@@@@@@@@@:  :+ :@@@@@@@@@@+  #@@@ #@@@ :@@@@      :@@@# #@@@@@@@@@+ @@@@: ::::
    ~~~~+@::+#:+@@@@@@@@@#     @@@@+  @@@@# :@@@@#@@@@ +@@@@:  :: +@@@+ @@@@+@@@@@: @@@#  @@@#
     ~~~~~:       :++++: :    #@@@@  +@@@@  @@@@@@@@@@: @@@@@@@@+ @@@@  @@@# #@@@@  @@@@##@@@:
        ~~~++++++++####+++    ####:  ####+ +@@@+  +@@@+ :#@@@@@@  @@@# :@#@:  @@@#   +#@@@@##


VCU Ram Racing Distribution Hub 2.0
===================================

The Distribution Hub 2.0 is the central power and signal board for VCU-04.
It sits between the M130 ECU and the rest of the wiring harness, switching power to the car's loads
and routing sensor, dash, and communication signals through a single board.

Contributors
------------

  Isaac Subudhi     Team Lead, and all sheets.
  Brandon Estrada   Low Power Relays
  Will Schindler    Status Indicators
  Jessie Vargas     ECU Interface (assist)


Documentation
-------------

A PDF and PNG images of every schematic sheet are in documentation/images.
They are regenerated automatically on each push to main.


Project Files
-------------

Open Hub-2.0.kicad_pro in KiCad. Schematics and the PCB are at the project root.
EasyEDA libraries and 3D models are included with the project.


Simulation
----------

Save and refill the PCB before launching KiPI.

  Linux:    ./simulation/run.sh
  Windows:  simulation\run.bat

Edit simulation/config.json for currents and model settings.
Comparison presets are in simulation/cases; tests are in simulation/tests.
See simulation/README.md for instructions and model assumptions.

Generated runs, downloaded tools, local environments, backups, and editor
history are ignored by Git. Keep board files, libraries, and configs tracked.
