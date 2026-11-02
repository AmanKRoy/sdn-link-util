#!/usr/bin/env python3
"""Link-utilisation demo: Mininet two-path topology, ONOS REST monitoring and rerouting.

    h1 - s1 - s2 - s4 - h2     primary path  (s1, s2, s4)
          \\ s3 /              alternate path (s1, s3, s4)

Inter-switch links are capped at CAP_MBPS. iperf offers LOAD_MBPS (90% of the cap)
from h1 to h2; the monitor reroutes h1->h2 traffic through s3 once s2 stays above 80%.
"""
import json
import os
import sys
import threading
import time

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo

import reroute as rr

OUT = os.environ.get("OUT", "/out")
CAP_MBPS = 10
LOAD_MBPS = 9
DURATION = 40
PRIMARY = ["s1", "s2", "s4"]
ALT = ["s1", "s3", "s4"]
H1, H2 = "10.0.0.1", "10.0.0.2"


class TwoPathTopo(Topo):
    def build(self):
        for i, n in enumerate(["s1", "s2", "s3", "s4"], 1):
            self.addSwitch(n, dpid="%016x" % i)
        self.addHost("h1", ip=H1 + "/24")
        self.addHost("h2", ip=H2 + "/24")
        self.addLink("h1", "s1")
        self.addLink("h2", "s4")
        for a, b in [("s1", "s2"), ("s2", "s4"), ("s1", "s3"), ("s3", "s4")]:
            self.addLink(a, b, bw=CAP_MBPS)


def banner(text):
    print("\n" + "=" * 70 + "\n" + text + "\n" + "=" * 70, flush=True)


def scenario(net):
    h1, h2 = net.get("h1", "h2")

    banner("STEP 1  Mininet two-path topology, controller = ONOS")
    for _ in range(60):
        if all(s.connected() for s in net.switches):
            break
        time.sleep(1)
    else:
        sys.exit("switches never connected to ONOS")
    net.pingAll(timeout=1)  # discovery warm-up, result ignored
    rr.wait_for_hosts([H1, H2])
    time.sleep(5)
    net.staticArp()
    links = rr.rest("GET", "/links")["links"]
    print("  switches connected: %d   ONOS links: %d" % (len(net.switches), len(links)))

    banner("STEP 2  Read port statistics: GET /onos/v1/statistics/ports")
    stats = rr.rest("GET", "/statistics/ports")
    with open(os.path.join(OUT, "statistics_ports.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("  saved %s (%d switches reporting)" % (os.path.join(OUT, "statistics_ports.json"),
                                                 len(stats["statistics"])))

    banner("STEP 3  Baseline: primary path via s2, forward and reverse")
    rr.install_path(PRIMARY, H1, H2, rr.BASE_PRIO)
    rr.install_path(PRIMARY[::-1], H2, H1, rr.BASE_PRIO)
    print(h1.cmd("ping -c3 -W1 %s" % H2))
    rr.save_flows("flows_before.json")

    banner("STEP 4  Generate load (iperf UDP %d Mbps) while monitor runs" % LOAD_MBPS)
    h2.cmd("iperf -s -u -i 1 > %s/iperf_server.txt 2>&1 &" % OUT)
    time.sleep(1)
    mon = threading.Thread(target=rr.monitor, daemon=True, kwargs=dict(
        src_ip=H1, dst_ip=H2, primary=PRIMARY, alt=ALT, cap_mbps=CAP_MBPS,
        threshold=0.8, duration=DURATION + 5))
    mon.start()
    client = h1.cmd("iperf -c %s -u -b %dM -t %d -i 1" % (H2, LOAD_MBPS, DURATION))
    mon.join()
    h2.cmd("pkill iperf")
    with open(os.path.join(OUT, "iperf_client.txt"), "w") as f:
        f.write(client)
    print(client.strip().splitlines()[-1] if client.strip() else "(no iperf output)")

    banner("STEP 5  Result: changed flows and reachability")
    rr.save_flows("flows_after.json")
    print(h1.cmd("ping -c3 -W1 %s" % H2))
    print("  flow rules per switch (before -> after):")
    before = json.load(open(os.path.join(OUT, "flows_before.json")))
    after = json.load(open(os.path.join(OUT, "flows_after.json")))
    for s in ["s1", "s2", "s3", "s4"]:
        print("  %s: %d -> %d" % (s, len(before[s]), len(after[s])))


def main():
    setLogLevel("warning")
    rr.wait_for_onos(["openflow-base", "lldpprovider", "hostprovider"])
    net = Mininet(
        topo=TwoPathTopo(),
        switch=lambda name, **kw: OVSSwitch(name, protocols="OpenFlow13",
                                            datapath=os.environ.get("OVS_DATAPATH", "user"), **kw),
        controller=None, link=TCLink, autoSetMacs=True, waitConnected=False)
    net.addController("onos", controller=RemoteController, ip="127.0.0.1", port=6653)
    net.start()
    try:
        scenario(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
