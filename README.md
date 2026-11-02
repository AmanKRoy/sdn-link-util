# SDN link utilisation monitor and rerouter

Course: 21CSE456T Software Defined Networks, scenario-based assessment (ONOS).

Tools: Mininet (two-path topology), ONOS 2.7.0 with the REST API, iperf, Python stdlib. Everything runs in Docker; nothing is installed on the host.

## Run
```
./run.sh   # starts ONOS and Mininet, runs the whole demo, saves out/
```
ONOS takes 2-5 minutes to start the first time; the script waits for it. Needs Docker (run with sudo if your user is not in the docker group). Cleanup: `docker rm -f sdn-mn sdn-onos`.

## What it does
1. Mininet topology: h1 - s1, then two paths to s4: s1-s2-s4 (primary) and s1-s3-s4 (alternate). Inter-switch links capped at 10 Mbps. h2 hangs off s4.
2. Reads port statistics with `GET /onos/v1/statistics/ports` (saved to `out/statistics_ports.json`).
3. Installs baseline flow rules for h1 <-> h2 over the primary path (priority 40000) via `POST /onos/v1/flows/{deviceId}`.
4. Starts iperf UDP from h1 to h2 at 9 Mbps (90% of the link). The monitor polls port stats every 2 s and computes transmit rate per port.
5. When the primary path stays above 80% for two polls, it posts higher-priority rules (priority 50000) that send h1 -> h2 traffic through s3. The alternate path is checked first and only used if it is below 80%.

## Show the examiner
- REST responses: `out/rest_calls.log` (every call and its HTTP status)
- Decision log: `out/decision_log.txt` (utilisation per poll, then the reroute decision)
- Changed flows: `out/flows_before.json` vs `out/flows_after.json`. s1, s3 and s4 each gain one priority-50000 rule for h1 -> h2 (s1 out to s3, s3 out to s4, s4 out to h2). s2 is unchanged. Flow counts include ONOS default rules.
- Traffic result: `out/iperf_client.txt`, `out/iperf_server.txt`
- Full run: `out/transcript.txt`

## Files
`topo_demo.py` (Mininet topology and scenario), `reroute.py` (ONOS REST client, monitor, rerouting, stdlib only), `Dockerfile`, `run.sh`, `out/` (captured run, git-ignored).

## Notes
- Rerouting uses flow rules, not intents. Flow rules were chosen because the path is explicit and the REST calls are easy to show.
- Static ARP is set on the hosts (`net.staticArp()`), so no ARP flows are needed. Only IPv4 rules are installed.
- ONOS port stats refresh in bursts. The monitor uses a 10 s rolling window, so the rate is smooth and a reroute happens about 15 s after load starts.
- Constants: `CAP_MBPS` (10), `LOAD_MBPS` (9), `DURATION` (40) in `topo_demo.py`; threshold 0.8, window 10 s, 3 consecutive polls in `monitor()` in `reroute.py`.
- `run.sh` uses sudo for Docker (user not in the docker group).
