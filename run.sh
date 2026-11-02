#!/bin/bash
# Usage: ./run.sh   (needs Docker; nothing is installed on the host)
set -eo pipefail
cd "$(dirname "$0")"
# Docker needs root unless the user is in the docker group; sudo prompts for the password on the user's own terminal.
DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo docker"
OUT=$PWD/out; mkdir -p "$OUT"
rm -f "$OUT"/decision_log.txt "$OUT"/rest_calls.log
$DOCKER build -q -t sdn-link-mn .
$DOCKER rm -f sdn-mn sdn-onos >/dev/null 2>&1 || true
$DOCKER run -d --name sdn-mn --privileged --network none -v "$OUT":/out sdn-link-mn sleep infinity >/dev/null
$DOCKER run -d --name sdn-onos --network container:sdn-mn -e ONOS_APPS=drivers,openflow,lldpprovider,hostprovider onosproject/onos:2.7.0 >/dev/null
$DOCKER exec sdn-mn bash -c 'mkdir -p /var/run/openvswitch; ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema 2>/dev/null; ovsdb-server --remote=punix:/var/run/openvswitch/db.sock --pidfile --detach; ovs-vsctl --no-wait init; ovs-vswitchd --pidfile --detach'
$DOCKER exec sdn-mn python3 /demo/topo_demo.py | tee "$OUT/transcript.txt"
$DOCKER exec sdn-mn mn -c >/dev/null 2>&1 || true
echo "Cleanup: docker rm -f sdn-mn sdn-onos"
