import logging
from subprocess import check_call
import os

def main():

    keystore_dir = '/workspaces/oracle-sandbox/keystore'
    pythd_ws_port = os.getenv('PYTHD_WS_PORT')
    secondary_solana_rpc_port = os.getenv('SECONDARY_SOLANA_RPC_PORT')

    logging.debug('Starting pythd')
    check_call([
        'pythd',
        '-r', 'localhost',
        '-s', f'localhost:{secondary_solana_rpc_port}',
        '-k', keystore_dir,
        '-x',
        '-m', 'finalized',
        '-d',
        '-p', str(pythd_ws_port),
        '-z'
    ])

    # pythd -r localhost -s localhost:8999 -k /workspaces/oracle-sandbox/keystore -x -m finalized -d -p 8910
    # gdb /home/pyth/pyth-client/debug/pythd
    # r -r localhost -s localhost:8999 -k /workspaces/oracle-sandbox/keystore -x -m finalized -d -p 8910

    # To close connection:
    # - Add iptables rule to prevent reconnection: 
    #   iptables -A test-firewall -p tcp --dport 8999 -j DROP
    # - Kill the connection:
    #   perl killcx.pl 127.0.0.1:8999

    # To reset iptables: iptables -F test-firewall

    # Situation: if primary goes down, no notify_price_sched updates are sent
    # Where are they being added? They _should_ always be being added to the primary? 


if __name__ == '__main__':
    main()
