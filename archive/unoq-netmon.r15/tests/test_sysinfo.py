import os

from overheard import sysinfo


def test_cpu_percent_from_two_readings():
    assert sysinfo.cpu_percent((100, 1000), (150, 1100)) == 50.0
    assert sysinfo.cpu_percent((100, 1000), (100, 1000)) == 0.0      # no time passed
    assert sysinfo.cpu_percent((100, 1000), (900, 1100)) == 100.0    # clamped


def test_reads_from_proc_style_files(tmp_path):
    stat = tmp_path / "stat"
    stat.write_text("cpu  100 0 100 700 100 0 0 0\ncpu0 1 1 1 1\n")
    assert sysinfo.read_cpu_times(str(stat)) == (200, 1000)
    mem = tmp_path / "meminfo"
    mem.write_text("MemTotal:        2000 kB\nMemFree:  100 kB\nMemAvailable:    500 kB\n")
    assert sysinfo.read_memory(str(mem)) == (1500 * 1024, 2000 * 1024)
    z = tmp_path / "zone0"
    z.mkdir()
    (z / "temp").write_text("52300\n")
    assert sysinfo.read_temperature(str(tmp_path / "zone*" / "temp")) == 52.3
    assert sysinfo.read_temperature(str(tmp_path / "nothing*" / "temp")) is None
    up = tmp_path / "uptime"
    up.write_text("3600.5 100.0\n")
    assert sysinfo.read_uptime(str(up)) == 3600.5


def test_bad_temperature_values_are_ignored(tmp_path):
    z = tmp_path / "zone0"
    z.mkdir()
    (z / "temp").write_text("garbage")
    assert sysinfo.read_temperature(str(tmp_path / "zone*" / "temp")) is None


def test_snapshot_keeps_a_bounded_history():
    v = sysinfo.Vitals()
    for i in range(200):
        v.cpu_hist.append(i)
    assert len(v.snapshot()["cpu_hist"]) == sysinfo.HISTORY


def test_real_sample_on_this_machine():
    if not os.path.exists("/proc/stat"):
        return
    v = sysinfo.Vitals()
    sysinfo.sample(v, sysinfo.read_cpu_times())
    s = v.snapshot()
    assert 0 <= s["cpu"] <= 100 and s["mem_total"] > 0 and s["disk_total"] > 0 and s["cores"] >= 1


def test_network_is_read_from_the_route_table(tmp_path):
    r = tmp_path / "route"
    r.write_text("Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
                 "eth0\t00000000\t0101A8C0\t0003\t0\t0\t700\t00000000\t0\t0\t0\n"
                 "wlan0\t00000000\t01204564\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
                 "wlan0\t00204564\t00000000\t0001\t0\t0\t600\t00F0FFFF\t0\t0\t0\n")
    assert sysinfo.read_default_route(str(r)) == ("wlan0", "100.69.32.1")
    assert sysinfo.read_default_route(str(tmp_path / "missing")) is None
    (tmp_path / "wlan0" / "wireless").mkdir(parents=True)
    net = sysinfo.read_network(str(r), str(tmp_path), run=lambda argv: "Dea\x07con\n")
    assert net["iface"] == "wlan0" and net["gateway"] == "100.69.32.1" and net["wireless"] is True
    assert net["ssid"] in ("Deacon", "")          # "" when no Wi-Fi tool is installed on this machine
    assert sysinfo.read_network(str(tmp_path / "missing")) == {}
    assert sysinfo._clean("a\x00b" + "x" * 50) == "ab" + "x" * 30
