from asyncio import subprocess
import json
import os
from subprocess import Popen, check_call, check_output
from tempfile import mkdtemp, mkstemp
import time
import logging

PYTH_CLIENT_PATH = '/home/pyth/pyth-client'

PRODUCTS = {
    'BTC': {
        'symbol': 'Crypto.BTC/USD',
    },
    'ETH': {
        'symbol': 'Crypto.ETH/USD',
    },
    'LTC': {
        'symbol': 'Crypto.LTC/USD',
    },
}

logging.basicConfig(level=logging.DEBUG)

def main():

    pythd_ws_port = os.getenv('PYTHD_WS_PORT')
    solana_rpc_port = os.getenv('SOLANA_RPC_PORT')

    # Start Solana Test Validator
    logging.debug('Starting Solana test validator')
    Popen([
        'solana-test-validator', '--rpc-port', str(solana_rpc_port), '--ledger', mkdtemp(prefix='stv_')], stdout=subprocess.DEVNULL)
    time.sleep(3)
    logging.debug('Started Solana test validator')
    
    # Generate keypair
    logging.debug('Generating keypair')
    cfg_dir = mkdtemp(prefix='cfg_')
    keypair_path = os.path.join(cfg_dir, 'id.json')
    keygen_output = check_output([
        'solana-keygen', 'new', '--no-passphrase', '--outfile', keypair_path
    ]).decode('ascii').splitlines()
    pub_key = [line for line in keygen_output if 'pubkey' in line][0].split('pubkey: ')[1]
    logging.debug('Generated keypair')

    # Airdrop some SOL to the publish key
    logging.debug('Airdropping SOL')
    check_call([
        'solana', 'airdrop', '100', pub_key,
        '--commitment', 'finalized',
        '--url', 'localhost',
        '--keypair', keypair_path,
    ])
    logging.debug('Airdropped SOL')

    # Deploy the program
    logging.debug('Deploying program')
    deploy_output = check_output([
        'solana', 'program', 'deploy',
        os.path.join(PYTH_CLIENT_PATH, 'target', 'deploy', 'pyth_oracle.so'),
        '--commitment', 'finalized',
        '--url', 'localhost',
        '--keypair', keypair_path,
    ]).decode('ascii').splitlines()
    program_key = [line for line in deploy_output if 'Program Id' in line][0].split('Program Id: ')[1]
    logging.debug('Deployed program')

    # Write program key to file
    logging.debug('Writing program key to file')
    pythd_dir = mkdtemp(prefix='pythd_')
    with open(os.path.join(pythd_dir, 'program_key.json'), 'w') as f:
        f.write(program_key)
    logging.debug('Wrote program key to file')

    # Create the symlink to the publish_key_pair.json
    logging.debug('Creating publish_key_pair.json symlink')
    path = os.path.join(pythd_dir, 'publish_key_pair.json')
    os.symlink(keypair_path, path)
    logging.debug('Created publish_key_pair.json symlink')

    # Init the mapping account
    logging.debug('Initializing mapping account')
    check_call([
        'pyth_admin', 'init_mapping',
        '-r', 'localhost',
        '-k', pythd_dir,
        '-c', 'finalized',
    ])
    logging.debug('Initialized mapping account')

    # Add the product accounts
    logging.debug('Adding product accounts')
    product_accounts = {
        product: check_output([
            'pyth_admin', 'add_product',
            '-r', 'localhost',
            '-k', pythd_dir,
            '-c', 'finalized',
        ]).decode('ascii').splitlines()[0]
        for product in PRODUCTS.keys()
    }
    logging.debug('Added product accounts')

    # Initialise the product accounts
    logging.debug('Initializing product accounts')
    products = []
    for product in PRODUCTS.keys():
        products.append({
            'account': product_accounts[product],
            'attr_dict': PRODUCTS[product],
        })
    fd, products_dir = mkstemp(suffix='.json', prefix='products_')
    with os.fdopen(fd, 'w') as f:
        json.dump(products, f)
    check_call([
        'pyth_admin', 'upd_product', products_dir,
        '-r', 'localhost',
        '-k', pythd_dir,
        '-c', 'finalized',
    ])
    os.remove(products_dir)
    logging.debug('Initialized product accounts')

    # Add the price accounts
    logging.debug('Adding price accounts')
    price_accounts = {
        product: check_output([
            'pyth_admin', 'add_price',
            product_account, 'price', '-e', '-5',
            '-r', 'localhost',
            '-k', pythd_dir,
            '-c', 'finalized',
            '-n',
        ]).decode('ascii').splitlines()[0]
        for product, product_account in product_accounts.items()
    }
    logging.debug('Added price accounts')

    # Permission the publisher for each price account
    logging.debug('Permissioning publisher for price accounts')
    for product, price_account in price_accounts.items():
        check_call([
            'pyth_admin', 'add_publisher',
            pub_key, price_account,
            '-r', 'localhost',
            '-k', pythd_dir,
            '-c', 'finalized',
            '-n',
        ])
    logging.debug('Permissioned publisher for price accounts')

    # Initialze the price accounts
    logging.debug('Initializing price accounts')
    for product, price_account in price_accounts.items():
        check_call([
            'pyth_admin', 'init_price',
            price_account, '-e', '-5',
            '-r', 'localhost',
            '-k', pythd_dir,
            '-c', 'finalized',
            '-n',
        ])
    logging.debug('Initialized price accounts')

    # Run pythd now everything has been set up
    logging.debug('Starting pythd')
    check_call([
        'pythd',
        '-r', 'localhost',
        '-k', pythd_dir,
        '-x',
        '-m', 'finalized',
        '-d',
        '-p', str(pythd_ws_port),
    ])

if __name__ == '__main__':
    main()
