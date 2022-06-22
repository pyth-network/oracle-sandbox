FROM docker.io/pythfoundation/pyth-client:devnet-v2.10.1

RUN sudo apt-get update && sudo apt-get install -y python3-pip libffi-dev valgrind htop iptables dsniff net-tools
RUN pip3 install pythclient solana

ARG SOLANA_RPC_PORT
ENV SOLANA_RPC_PORT=$SOLANA_RPC_PORT

ARG SECONDARY_SOLANA_RPC_PORT
ENV SECONDARY_SOLANA_RPC_PORT=$SECONDARY_SOLANA_RPC_PORT

ARG PYTHD_WS_PORT
ENV PYTHD_WS_PORT=$PYTHD_WS_PORT

ENV PATH="/home/pyth/pyth-client/build:${PATH}"
ENTRYPOINT [ "python3", "main.py" ]
