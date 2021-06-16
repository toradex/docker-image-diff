FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y \
     --no-install-recommends --no-install-suggests \
    git python3-minimal python3-setuptools python3-pip \
    && apt-get clean && apt-get autoremove \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install six docker quantiphy

COPY docker-image-diff.py /
ENTRYPOINT ["/usr/bin/python3","/docker-image-diff.py"]



