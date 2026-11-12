.. zephyr:code-sample:: pytest_shell
   :name: Pytest shell application testing

   Execute pytest tests against the Zephyr shell.

Overview
********

The sample project illustrates usage of pytest framework integrated with
Twister test runner.

A simple application provides basic Zephyr shell interface. Twister builds it
and then calls pytest in subprocess which runs tests from
``pytest/test_shell.py`` file. The first test verifies valid response for
``help`` command, second one verifies if application is able to return
information about used kernel version. Both tests use ``shell`` fixture, which
is defined in ``pytest-twister-harness`` plugin. More information about plugin
can be found :ref:`here <integration_with_pytest>`.

Requirements
************

Board (hardware, ``native_sim`` or ``QEMU``) with UART console.

Building and Running
********************

Build and run sample by Twister:

.. code-block:: console

   $ ./scripts/twister -vv --platform native_sim -T samples/subsys/testsuite/pytest/shell

Running the pnet tests on hardware with PowerShell
=================================================

The following example runs the ``pnet`` tests directly against an existing
hardware build. Run it from the workspace root (the directory containing
``zephyr`` and ``.venv``). The virtual environment must already contain
``west``, pytest, and the dependencies required by the Twister harness. The
build must contain the ``pnet`` shell commands, and the board, serial port,
and ``nrfutil`` runner must be available.

If PowerShell permits running activation scripts, activate the environment:

.. code-block:: powershell

   .\.venv\Scripts\Activate.ps1

If script execution is disabled, leave the execution policy unchanged and
instead add the environment's ``Scripts`` directory to ``PATH`` for this
session:

.. code-block:: powershell

   $env:PATH = "$PWD\.venv\Scripts;$env:PATH"

Then, in the same PowerShell session, configure the harness and run the tests:

.. code-block:: powershell

   $env:PATH = "$env:USERPROFILE\.nrfutil\bin;$env:PATH"
   $env:ZEPHYR_BASE = "$PWD\zephyr"
   $env:PYTHONPATH = "$env:ZEPHYR_BASE\scripts\pylib\pytest-twister-harness\src;$env:PYTHONPATH"
   west --version
   nrfutil --version

   .\.venv\Scripts\python.exe -m pytest -v -ra --twister-harness `
       --device-type=hardware --device-serial=COM16 --runner=nrfutil `
       --device-id=001051868933 --dut-scope=session `
       --build-dir="$PWD\zephyr_wifi_examples\build" `
       "$PWD\zephyr\samples\subsys\testsuite\pytest\shell\pytest\test_shell.py" -k pnet

Replace the build directory, COM port, device ID, and runner with those for
your setup. If ``nrfutil`` is installed elsewhere, add its actual directory to
``PATH`` instead. The hardware harness uses ``west flash`` to flash the existing
build. The environment settings above apply to the current PowerShell session.

This example relies on pytest automatically loading the harness plugin from the
workspace environment. Do not also pass ``-p twister_harness.plugin`` when it
is automatically loaded, as that registers the plugin twice. If the plugin is
not automatically loaded in your environment, add that option to the command.
``No module named 'twister_harness'`` indicates that the harness source path
is not available to Python; ``west not found`` means that ``west`` is not on
``PATH``. Activating the environment adds its ``Scripts`` directory to
``PATH``. If ``west flash`` reports that ``nrfutil`` was not found, add its
installation directory to ``PATH`` and check ``nrfutil --version``.

Set ``PNET_SSID`` and, for a secured network, ``PNET_PSK`` in the PowerShell
session for Wi-Fi tests; otherwise those tests are skipped. Avoid sharing the
password in logs or scripts. Additional tests require the following environment
variables:

* ``PNET_SERVER_IP`` and ``PNET_TCP_PORT`` or ``PNET_UDP_PORT`` for TCP or UDP
  echo tests, respectively, with reachable echo servers.
* ``PNET_DNS_HOST`` to override the default DNS host, ``www.google.com``.
* ``PNET_MQTT_HOST`` and ``PNET_MQTT_PORT`` for MQTT tests; optionally set
  ``PNET_MQTT_TOPIC``.
* ``PNET_BSSID`` to test a specific access point.
* ``PNET_ENABLE_SOAK=1`` or ``PNET_ENABLE_SUITE=1`` to enable the longer soak
  tests or built-in suite, respectively.

The disruptive ``pnet assert`` and ``pnet reset`` tests are intentionally
skipped because they require a dedicated recovery test.


Sample Output
=============

.. code-block:: console

    ...
    samples/subsys/testsuite/pytest/shell/pytest/test_shell.py::test_shell_print_help
    INFO: send "help" command
    DEBUG: #: uart:~$ help
    DEBUG: #: Please press the <Tab> button to see all available commands.
    DEBUG: #: You can also use the <Tab> button to prompt or auto-complete all commands or its subcommands.
    DEBUG: #: You can try to call commands with <-h> or <--help> parameter for more information.
    DEBUG: #: Shell supports following meta-keys:
    DEBUG: #: Ctrl + (a key from: abcdefklnpuw)
    DEBUG: #: Alt  + (a key from: bf)
    DEBUG: #: Please refer to shell documentation for more details.
    DEBUG: #: Available commands:
    DEBUG: #: clear    :Clear screen.
    DEBUG: #: device   :Device commands
    DEBUG: #: devmem   :Read/write physical memory
    DEBUG: #:             Usage:
    DEBUG: #:             Read memory at address with optional width:
    DEBUG: #:             devmem address [width]
    DEBUG: #:             Write memory at address with mandatory width and value:
    DEBUG: #:             devmem address <width> <value>
    DEBUG: #: help     :Prints the help message.
    DEBUG: #: history  :Command history.
    DEBUG: #: kernel   :Kernel commands
    DEBUG: #: rem      :Ignore lines beginning with 'rem '
    DEBUG: #: resize   :Console gets terminal screen size or assumes default in case the
    DEBUG: #:             readout fails. It must be executed after each terminal width change
    DEBUG: #:             to ensure correct text display.
    DEBUG: #: retval   :Print return value of most recent command
    DEBUG: #: shell    :Useful, not Unix-like shell commands.
    DEBUG: #: uart:~$
    INFO: response is valid
    PASSED
    samples/subsys/testsuite/pytest/shell/pytest/test_shell.py::test_shell_print_version
    INFO: send "kernel version" command
    DEBUG: #: uart:~$ kernel version
    DEBUG: #: Zephyr version 3.5.99
    DEBUG: #: uart:~$
    INFO: response is valid
    PASSED
    ...
