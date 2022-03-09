FROM docker.io/pythfoundation/pyth-client:devnet-v2.10.1

COPY main.py .

ARG SOLANA_RPC_PORT
ENV SOLANA_RPC_PORT=$SOLANA_RPC_PORT

ARG PYTHD_WS_PORT
ENV PYTHD_WS_PORT=$PYTHD_WS_PORT

ENV PATH="/home/pyth/pyth-client/build:${PATH}"
ENTRYPOINT [ "python3", "main.py" ]
