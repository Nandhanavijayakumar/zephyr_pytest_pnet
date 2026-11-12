# Copyright (c) 2023 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import re
import time
import uuid

import pytest

from twister_harness import Shell
from twister_harness.exceptions import TwisterHarnessTimeoutException

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def settle_after_test():
    yield
    time.sleep(1)


def test_shell_print_help(shell: Shell):
    logger.info('send "help" command')
    lines = shell.exec_command('help')
    assert 'Available commands:' in lines, 'expected response not found'
    logger.info('response is valid')


def test_shell_print_version(shell: Shell):
    logger.info('send "kernel version" command')
    lines = shell.exec_command('kernel version')
    assert any(['Zephyr version' in line for line in lines]), 'expected response not found'
    logger.info('response is valid')


class PnetShell(Shell):
    synchronized = True

    def exec_command(self, command: str, timeout: float | None = None,
                     print_output: bool = True) -> list[str]:
        if not self.synchronized:
            pytest.skip('UART command synchronization was lost in an earlier test')
        marker = f'PNET{uuid.uuid4().hex[:12]}'
        self._device.clear_buffer()
        self._device.write(f'{command}\nshell echo {marker}\n'.encode())
        try:
            return self._device.readlines_until(regex=re.escape(marker),
                                                timeout=timeout or self.base_timeout,
                                                print_output=print_output)
        except TwisterHarnessTimeoutException:
            self.synchronized = False
            raise


@pytest.fixture(scope='session')
def pnet_shell(shell: Shell, dut):
    interface = PnetShell(dut, prompt=shell.prompt, timeout=60)
    try:
        interface.exec_command('shell echo off')
        output = '\n'.join(interface.exec_command('shell echo'))
        assert 'Echo status: off' in output, 'Unable to disable shell echo'
        yield interface
    finally:
        if interface.synchronized:
            interface.exec_command('shell echo on')
        else:
            dut.write(b'shell echo on\n')


def test_pnet_help(pnet_shell: Shell):
    lines = pnet_shell.exec_command('pnet')
    output = '\n'.join(lines)
    assert 'pnet - pnet commands' in output
    assert 'fw_version' in output
    assert 'test_run_all' in output


@pytest.fixture(scope='session')
def pnet_initialized(pnet_shell: Shell):
    output = '\n'.join(pnet_shell.exec_command('pnet init', timeout=90))
    assert 'wifi initialize successful:' in output, output
    time.sleep(2)
    version = '\n'.join(pnet_shell.exec_command('pnet fw_version', timeout=60))
    assert 'WiFi driver version:' in version, version
    return pnet_shell


def test_pnet_fw_version(pnet_initialized: Shell):
    lines = pnet_initialized.exec_command('pnet fw_version', timeout=60)
    output = '\n'.join(lines)
    assert 'WiFi driver version:' in output
    assert 'WiFi firmware version:' in output


def shell_argument(value: str) -> str:
    if any(character in value for character in ('"', '\\', '\n', '\r')):
        raise ValueError('Shell arguments must not contain quotes, backslashes, or newlines')
    return f'"{value}"'


def command(shell: Shell, text: str, expected: str, timeout: int = 60) -> str:
    output = '\n'.join(shell.exec_command(text, timeout=timeout))
    assert expected in output, f'Expected {expected!r} in output:\n{output}'
    return output


def connect_wifi(shell: Shell, dut, bssid: str | None = None):
    ssid = os.environ.get('PNET_SSID')
    if not ssid:
        pytest.skip('Set PNET_SSID and optionally PNET_PSK for Wi-Fi tests')
    psk = os.environ.get('PNET_PSK', '')
    arguments = [shell_argument(ssid)]
    if psk:
        arguments.append(shell_argument(psk))
    if bssid:
        arguments.append(shell_argument(bssid))
    subcommand = 'connect_bssid' if bssid else 'connect'
    lines = shell.exec_command(f'pnet {subcommand} {" ".join(arguments)}', timeout=30,
                               print_output=False)
    output = '\n'.join(lines)
    assert 'Connect request sent' in output, 'Wi-Fi connect request failed'
    if 'IP configuration applied to interface' not in output:
        try:
            lines += dut.readlines_until(regex='IP configuration applied to interface',
                                          timeout=90, print_output=False)
        except TwisterHarnessTimeoutException:
            pytest.fail('Wi-Fi did not report IP configuration within 90 seconds')
    time.sleep(10)


@pytest.fixture(scope='session')
def pnet_online(pnet_initialized: Shell, dut):
    connect_wifi(pnet_initialized, dut)
    return pnet_initialized


def endpoint(port_name: str):
    host = os.environ.get('PNET_SERVER_IP')
    port = os.environ.get(port_name)
    if not host or not port:
        pytest.skip(f'Set PNET_SERVER_IP and {port_name} for this test')
    import ipaddress
    try:
        ipaddress.IPv4Address(host)
        port_number = int(port)
        if not 1 <= port_number <= 65535:
            raise ValueError('port out of range')
    except ValueError:
        pytest.fail(f'Invalid PNET_SERVER_IP or {port_name}')
    return host, port_number


def dns_host():
    return shell_argument(os.environ.get('PNET_DNS_HOST', 'www.google.com'))


def test_pnet_interface_cycle(pnet_initialized: Shell):
    try:
        command(pnet_initialized, 'pnet iface_down', 'net_if_down() returned 0', timeout=90)
        time.sleep(2)
    finally:
        command(pnet_initialized, 'pnet iface_up', 'net_if_up() returned 0', timeout=90)
        time.sleep(2)


def test_pnet_connect(pnet_online: Shell):
    assert pnet_online is not None


def test_pnet_resolve_sync(pnet_online: Shell):
    output = command(pnet_online, f'pnet resolve {dns_host()} sync', 'A:', timeout=60)
    assert re.search(r'\bA:\s+\d+\.\d+\.\d+\.\d+', output), output


def test_pnet_resolve_async(pnet_online: Shell, dut):
    lines = pnet_online.exec_command(f'pnet resolve {dns_host()} async', timeout=30)
    output = '\n'.join(lines)
    assert 'DNS query sent' in output, output
    if not re.search(r'DNS resolve (?:complete|failed)', output):
        try:
            lines += dut.readlines_until(regex=r'DNS resolve (?:complete|failed)', timeout=30)
        except TwisterHarnessTimeoutException:
            pytest.fail('Asynchronous DNS did not complete within 30 seconds')
    output = '\n'.join(lines)
    assert 'DNS resolve complete' in output, output
    assert re.search(r'\bA:\s+\d+\.\d+\.\d+\.\d+', output), output


@pytest.mark.parametrize('state', [0, 1])
def test_pnet_power_save(pnet_online: Shell, state: int):
    try:
        command(pnet_online, f'pnet ps {state}', 'Done')
    finally:
        command(pnet_online, 'pnet ps 0', 'Done')


def test_pnet_power_save_defaults(pnet_online: Shell):
    command(pnet_online, 'pnet psr', 'Wifi power save configs setup done')


def test_pnet_listen_interval(pnet_online: Shell):
    command(pnet_online, 'pnet ps_li 10', 'Done')


def test_pnet_tcp_echo(pnet_online: Shell):
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet tcp_connect {host} {port}', 'TCP connect successful')
    try:
        command(pnet_online, 'pnet tcp_tx pytest-pnet', 'TCP send successful')
        command(pnet_online, 'pnet tcp_rx', 'TCP recv: pytest-pnet')
    finally:
        command(pnet_online, 'pnet tcp_disconnect', 'TCP disconnect successful')


def test_pnet_tcp_id_echo_and_loop(pnet_online: Shell):
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet tcp_connect_id 1 {host} {port}', 'TCP connect successful')
    try:
        command(pnet_online, 'pnet tcp_tx_id 1 pytest-id', 'TCP send successful')
        command(pnet_online, 'pnet tcp_rx_id 1', 'TCP recv: pytest-id')
        command(pnet_online, 'pnet tcp_tx_loop_id 1 3 100 PING',
                'TEST_END,TC-TCP-TX-LOOP-ID,id=1,result=PASS')
    finally:
        command(pnet_online, 'pnet tcp_disconnect_id 1', 'TCP disconnect successful')


def test_pnet_udp_echo(pnet_online: Shell):
    host, port = endpoint('PNET_UDP_PORT')
    command(pnet_online, f'pnet udp_connect {host} {port}', 'UDP connect successful')
    try:
        command(pnet_online, 'pnet udp_tx pytest-udp', 'UDP send successful')
        command(pnet_online, 'pnet udp_rx 10000', 'data: pytest-udp', timeout=20)
    finally:
        command(pnet_online, 'pnet udp_disconnect', 'UDP disconnect successful')


def test_pnet_tcp_loop(pnet_online: Shell):
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet tcp_connect {host} {port}', 'TCP connect successful')
    try:
        command(pnet_online, f'pnet test_tcp_loop {host} {port} 3 100 PING',
                'TEST_END,TC-TCP-LOOP,result=PASS')
    finally:
        command(pnet_online, 'pnet tcp_disconnect', 'TCP disconnect successful')


@pytest.mark.parametrize('mode', ['sync', 'async', 'mixed'])
def test_pnet_dns_loop(pnet_online: Shell, mode: str):
    command(pnet_online, f'pnet test_dns_loop {dns_host()} {mode} 3 100',
            'TEST_END,TC-DNS-LOOP,result=PASS', timeout=90)


def test_pnet_ps_toggle(pnet_online: Shell):
    command(pnet_online, 'pnet test_ps_toggle 3 300 300',
            'TEST_END,TC-PS-TOGGLE,result=PASS', timeout=90)


def test_pnet_run_tcp_case(pnet_online: Shell):
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet tcp_connect {host} {port}', 'TCP connect successful')
    try:
        command(pnet_online, f'pnet test_run TC-003 {host} {port} 3 100',
                'TEST_END,TC-TCP-LOOP,result=PASS')
    finally:
        command(pnet_online, 'pnet tcp_disconnect', 'TCP disconnect successful')


def test_pnet_run_dns_case(pnet_online: Shell):
    command(pnet_online, f'pnet test_run TC-004 {dns_host()} sync 3 100',
            'TEST_END,TC-DNS-LOOP,result=PASS', timeout=90)


def test_pnet_run_ps_enable_case(pnet_online: Shell):
    try:
        command(pnet_online, 'pnet test_run TC-005', 'TEST_END,TC-005,result=PASS')
    finally:
        command(pnet_online, 'pnet ps 0', 'Done')


def test_pnet_run_idle_tcp_case(pnet_online: Shell):
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet test_run TC-008 {host} {port} PING 1500',
            'TEST_END,TC-008,result=PASS', timeout=90)


def test_pnet_run_ps_toggle_case(pnet_online: Shell):
    command(pnet_online, 'pnet test_run TC-010 3 300 300',
            'TEST_END,TC-PS-TOGGLE,result=PASS', timeout=90)


@pytest.mark.parametrize('use_test_run', [False, True], ids=['direct', 'TC-018'])
def test_pnet_soak(pnet_online: Shell, use_test_run: bool):
    if os.environ.get('PNET_ENABLE_SOAK') != '1':
        pytest.skip('Set PNET_ENABLE_SOAK=1 to run the soak tests')
    host, port = endpoint('PNET_TCP_PORT')
    prefix = 'test_run TC-018' if use_test_run else 'test_soak'
    output = command(pnet_online, f'pnet {prefix} 30 {host} {port} {dns_host()} 1000',
                     'TEST_END,TC-SOAK,result=PASS', timeout=120)
    assert re.search(r'TEST_RESULT,TC-SOAK-TCP,pass=[1-9]\d*,fail=0', output), output
    assert re.search(r'TEST_RESULT,TC-SOAK-DNS,pass=[1-9]\d*,fail=0', output), output


def test_pnet_suite_and_summary(pnet_online: Shell):
    if os.environ.get('PNET_ENABLE_SUITE') != '1':
        pytest.skip('Set PNET_ENABLE_SUITE=1 to run the full built-in suite')
    host, port = endpoint('PNET_TCP_PORT')
    command(pnet_online, f'pnet tcp_connect {host} {port}', 'TCP connect successful')
    output = command(pnet_online, f'pnet test_run_all {host} {port} {dns_host()} 30 1000',
                     'TEST_SUITE_END,PHASE1_TC_MAP,result=PASS', timeout=480)
    assert re.search(r'TEST_SUITE_SUMMARY,pass=6,fail=0,skip=17,total=23,verdict=PASS', output)
    summary = command(pnet_online, 'pnet test_summary', 'TEST_SUITE_SUMMARY,')
    assert 'fail=0,skip=17,total=23,verdict=PASS' in summary, summary


def test_pnet_mqtt(pnet_online: Shell):
    host = os.environ.get('PNET_MQTT_HOST')
    port = os.environ.get('PNET_MQTT_PORT')
    if not host or not port:
        pytest.skip('Set PNET_MQTT_HOST and PNET_MQTT_PORT for MQTT tests')
    try:
        if not 1 <= int(port) <= 65535:
            raise ValueError('port out of range')
    except ValueError:
        pytest.fail('Invalid PNET_MQTT_PORT')
    topic = shell_argument(os.environ.get('PNET_MQTT_TOPIC', 'pnet/pytest'))
    command(pnet_online, f'pnet mqtt_connect {shell_argument(host)} {port} pnet-pytest',
            'MQTT connect successful:', timeout=120)
    try:
        command(pnet_online, f'pnet mqtt_subscribe {topic} 1',
                'MQTT subscribe successful:', timeout=90)
        command(pnet_online, f'pnet mqtt_publish {topic} pytest-message 1',
                'MQTT publish successful:', timeout=90)
    finally:
        command(pnet_online, 'pnet mqtt_disconnect', 'MQTT disconnect successful', timeout=90)


def test_pnet_connect_bssid(pnet_online: Shell, dut):
    bssid = os.environ.get('PNET_BSSID')
    if not bssid:
        pytest.skip('Set PNET_BSSID to test connection to a specific access point')
    if not re.fullmatch(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}', bssid):
        pytest.fail('PNET_BSSID must be a colon-separated MAC address')
    command(pnet_online, 'pnet iface_down', 'net_if_down() returned 0', timeout=90)
    time.sleep(2)
    command(pnet_online, 'pnet iface_up', 'net_if_up() returned 0', timeout=90)
    time.sleep(2)
    connect_wifi(pnet_online, dut, bssid=bssid)


@pytest.mark.parametrize('subcommand', ['assert', 'reset'])
def test_pnet_disruptive_command(subcommand: str):
    pytest.skip(f'pnet {subcommand} is disruptive and requires a dedicated recovery test')
