# Oracle Sandbox

This image:
- Spins up a containerized Solana instance using `solana-test-validator`.
- Deploys the Pyth Oracle program to the Solana instance.
- Bootstraps the on-chain accounts necessary to publish Pyth prices. The `PRODUCTS` dictionary in [main.py](main.py) determines which products are bootstrapped.
- Runs an instance of Pythd against the Solana instance.

```bash
export SOLANA_RPC_PORT=8899
export PYTHD_WS_PORT=8910

docker build . -t oracle-sandbox --build-arg SOLANA_RPC_PORT=$SOLANA_RPC_PORT --build-arg PYTHD_WS_PORT=$PYTHD_WS_PORT
docker run -p $SOLANA_RPC_PORT:$SOLANA_RPC_PORT -p $PYTHD_WS_PORT:$PYTHD_WS_PORT oracle-sandbox 
```

The websocket API will start serving requests after the accounts have been bootstrapped and Pythd is running. 
