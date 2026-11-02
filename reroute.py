#!/usr/bin/env python3
"""Link-utilisation monitor and rerouter. Uses only the ONOS REST API (stdlib, no Mininet).

Polls GET /statistics/ports, computes transmit rate per switch port, and when the
primary path stays above THRESHOLD of CAP_MBPS for CONSEC polls, POSTs higher-priority
flow rules that steer traffic over the alternate path.
"""
import base64
import json
import os
import time
import urllib.request

ONOS = os.environ.get("ONOS_URL", "http://127.0.0.1:8181/onos/v1")
AUTH = "Basic " + base64.b64encode(b"onos:rocks").decode()
OUT = os.environ.get("OUT", "/out")
BASE_PRIO = 40000
REROUTE_PRIO = 50000


def log(msg):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(os.path.join(OUT, "decision_log.txt"), "a") as f:
        f.write(line + "\n")


def rest(method, path, body=None):
    headers = {"Authorization": AUTH, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ONOS + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        status = r.status
    with open(os.path.join(OUT, "rest_calls.log"), "a") as f:
        f.write("%s %s -> %d\n" % (method, path, status))
    return json.loads(raw) if raw else {}


def wait_for_onos(apps, tries=180):
    print("Waiting for ONOS apps %s" % ", ".join(apps), end="", flush=True)
    for _ in range(tries):
        try:
            active = {a["name"] for a in rest("GET", "/applications")["applications"] if a["state"] == "ACTIVE"}
            if all("org.onosproject." + x in active for x in apps):
                print(" up")
                return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    raise SystemExit("ONOS apps not active")


def wait_for_hosts(ips, tries=60):
    for _ in range(tries):
        seen = {ip for h in rest("GET", "/hosts")["hosts"] for ip in h["ipAddresses"]}
        if all(ip in seen for ip in ips):
            return
        time.sleep(1)
    raise SystemExit("ONOS never learned hosts %s" % ips)


def dev(name):
    """'s2' -> 'of:0000000000000002' (matches dpid in topo_demo.py)."""
    return "of:%016x" % int(name[1:])


def port_map():
    """(src device, dst device) -> egress port on src, from ONOS link view."""
    return {(l["src"]["device"], l["dst"]["device"]): l["src"]["port"]
            for l in rest("GET", "/links")["links"]}


def host_location(ip):
    for h in rest("GET", "/hosts")["hosts"]:
        if ip in h["ipAddresses"]:
            loc = h["locations"][0]
            return loc["elementId"], loc["port"]
    raise SystemExit("host %s unknown to ONOS" % ip)


def counters():
    """(device, port) -> bytes transmitted by that switch port."""
    out = {}
    for s in rest("GET", "/statistics/ports")["statistics"]:
        for p in s["ports"]:
            out[(s["device"], str(p["port"]))] = p.get("bytesSent", 0)
    return out


def flow(device, src_ip, dst_ip, port, prio):
    return {
        "priority": prio, "timeout": 0, "isPermanent": True, "deviceId": device,
        "treatment": {"instructions": [{"type": "OUTPUT", "port": str(port)}]},
        "selector": {"criteria": [
            {"type": "ETH_TYPE", "ethType": "0x0800"},
            {"type": "IPV4_SRC", "ip": src_ip + "/32"},
            {"type": "IPV4_DST", "ip": dst_ip + "/32"},
        ]},
    }


def install_path(path, src_ip, dst_ip, prio):
    """Install forward rules src_ip -> dst_ip along path (switch names, last one hosts dst_ip)."""
    links = port_map()
    devs = [dev(n) for n in path]
    dst_dev, dst_port = host_location(dst_ip)
    assert devs[-1] == dst_dev, "path must end at the switch of %s" % dst_ip
    for i, d in enumerate(devs):
        out = links[(d, devs[i + 1])] if i + 1 < len(devs) else dst_port
        rest("POST", "/flows", {"flows": [flow(d, src_ip, dst_ip, out, prio)]})
    log("installed %s -> %s via %s (priority %d)" % (src_ip, dst_ip, "-".join(path), prio))


def save_flows(name, switches=("s1", "s2", "s3", "s4")):
    result = {}
    for s in switches:
        result[s] = [f for f in rest("GET", "/flows/" + dev(s))["flows"]
                     if f.get("state") != "PURGED"]
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(result, f, indent=2)
    return result


def path_links(path, links):
    return [(dev(path[i]), links[(dev(path[i]), dev(path[i + 1]))]) for i in range(len(path) - 1)]


def monitor(src_ip, dst_ip, primary, alt, cap_mbps, threshold, duration,
            poll=1.0, window=10.0, consec=3):
    """Rate = byte delta over a rolling window; ONOS refreshes port stats in bursts, so one poll is noisy."""
    links = port_map()
    prim_links = path_links(primary, links)
    alt_links = path_links(alt, links)
    hist, over, rerouted = [], 0, False
    end = time.time() + duration
    log("monitor start: primary %s, alternate %s, cap %s Mbps, threshold %d%%, window %ss"
        % ("-".join(primary), "-".join(alt), cap_mbps, threshold * 100, window))
    while time.time() < end:
        now = time.time()
        hist.append((now, counters()))
        while len(hist) > 2 and hist[1][0] <= now - window:
            hist.pop(0)
        if len(hist) >= 2:
            t0, c0 = hist[0]
            cur = hist[-1][1]
            dt = now - t0

            def util(lks):
                rates = [(cur.get(k, 0) - c0.get(k, 0)) * 8 / dt / 1e6 for k in lks]
                return max(rates) / cap_mbps

            pu, au = util(prim_links), util(alt_links)
            state = "rerouted" if rerouted else "primary"
            log("util primary=%3.0f%% alternate=%3.0f%% window=%.0fs state=%s"
                % (pu * 100, au * 100, dt, state))
            if not rerouted and dt >= window * 0.8:
                over = over + 1 if pu > threshold else 0
                if over >= consec:
                    if au < threshold:
                        log("DECISION primary above %d%% for %d polls -> reroute to %s"
                            % (threshold * 100, consec, "-".join(alt)))
                        install_path(alt, src_ip, dst_ip, REROUTE_PRIO)
                        rerouted = True
                    else:
                        log("primary above threshold but alternate also busy, no change")
        time.sleep(poll)
    log("monitor stop, rerouted=%s" % rerouted)
    return rerouted
