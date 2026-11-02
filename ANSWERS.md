# Answers

## i. ONOS northbound interfaces available to the team
- **REST API** (`/onos/v1/...`, JSON, HTTP basic auth, default user `onos`). Covers devices, links, hosts, flows, intents, statistics, applications and network configuration.
- **Java API**: OSGi services (topology, device, host, link, flow rule, intent, statistics) for native applications.
- **Karaf CLI** (`ssh -p 8101 onos@<host>`): commands such as `devices`, `links`, `flows`, `apps`, `intents`.
- **Web GUI**: topology view, flow tables, and application management on port 8181.

## ii. REST-based external application vs native ONOS (OSGi/Karaf) application
| Aspect | External REST client | Native OSGi app |
|---|---|---|
| Language | Any (here Python stdlib) | Java only |
| Coupling | Uses the public API; survives ONOS upgrades more easily | Uses internal services; tied to the ONOS version and its bundles |
| Deployment | Runs anywhere that can reach ONOS | Packaged as an OSGi bundle, installed in Karaf |
| Data access | Polls statistics (latency = poll interval) | Can subscribe to listeners (events, lower latency) |
| Failure | Crash does not affect ONOS | Bad code can affect the controller |
| Effort here | Small script, easy to demo with curl | More code, build tooling, and bundle lifecycle |

For this task the REST client is the better fit: it is small, decoupled, and each step can be shown with curl. A native app would react faster to link events.

## iii. ONOS services the application uses
- **Statistics service**: port counters from `GET /onos/v1/statistics/ports`. Transmit rate is the delta of `bytesSent` over time, divided by link capacity.
- **Topology / link service**: `GET /onos/v1/links` gives the egress port for each switch-to-switch hop, so the script builds paths from port numbers ONOS reports.
- **Host service**: `GET /onos/v1/hosts` gives the switch and port where h2 attaches.
- **Flow rule service**: `POST /onos/v1/flows/{deviceId}` installs a higher-priority rule on each switch along the alternate path, which takes effect ahead of the baseline rule.
- **Intent service** (not used): an alternative for path changes, `POST /onos/v1/intents`, where ONOS computes and installs the path itself.
