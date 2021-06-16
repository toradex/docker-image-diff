FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y \
     --no-install-recommends --no-install-suggests \
    git python3-minimal python3-setuptools python3-pip \
    && apt-get clean && apt-get autoremove \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install six docker quantiphy

# used for validation
RUN pip install pylint mypy pydocstyle radon
# used for refactoring etc.
RUN pip install rope


