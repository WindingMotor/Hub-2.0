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


Prism Collaboration
-------------------

Project: https://ramracing-prism.larkspurindustries.com/project/prj_d483e5fd3cd7

.prism.json maps this repository's schematic, PCB, README, and design outputs
for Prism, including when browsing a specific Git revision.

The Assembly Assistant reads Design-Outputs/ibom.html. After changing the PCB,
regenerate it on Linux with KiCad installed:

  ./scripts/generate-assembly.sh

The script downloads a pinned version of InteractiveHtmlBom into a temporary
directory and generates a self-contained assembly page. Commit the updated
HTML together with the PCB so both describe the same revision. These assembly
outputs assist placement; they do not replace electrical/design review.

See documentation/PRISM.md for revision reviews, automatic assembly/docs updates,
KiCad Remote Symbols, simulation provenance and report sharing, and Release Studio.
