FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      mininet openvswitch-switch iproute2 iputils-ping iputils-arping python3 procps curl iperf \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /demo
COPY topo_demo.py reroute.py ./
CMD ["sleep", "infinity"]
