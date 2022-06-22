from asyncio import subprocess
import json
import os
from subprocess import Popen, check_call, check_output
from tempfile import mkdtemp, mkstemp
import time
import logging
from typing import Dict
import pythclient
from pythclient.pythclient import PythClient
from pythclient.pythaccounts import PythMappingAccount, PythPriceAccount, PythProductAccount
import asyncio
import solana
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.api import Client
from solana.system_program import CreateAccountParams, create_account
from solana.transaction import Transaction, TransactionInstruction, AccountMeta
from solana.rpc.types import TxOpts
import base64
from construct import Bytes, Int32sl, Int32ul, Struct

PYTH_CLIENT_PATH = '/home/pyth/pyth-client'
COMMAND_INIT_MAPPING = 0
COMMAND_ADD_PRODUCT = 2
COMMAND_UPD_PRODUCT = 3
COMMAND_ADD_PRICE = 4
COMMAND_ADD_PUBLISHER = 5
COMMAND_DEL_PUBLISHER = 6
PRICE_TYPE_PRICE = 1
PROGRAM_VERSION = 2

PRODUCTS = {
    'BTC': {
        'symbol': 'Crypto.BTC/USD',
    },
    # 'ETH': {
    #     'symbol': 'Crypto.ETH/USD',
    # },
    # 'LTC': {
    #     'symbol': 'Crypto.LTC/USD',
    # },
}

logging.basicConfig(level=logging.DEBUG)

async def main():

    keystore_dir = '/workspaces/oracle-sandbox/keystore'
    pythd_ws_port = os.getenv('PYTHD_WS_PORT')
    solana_rpc_port = os.getenv('SOLANA_RPC_PORT')
    solana_ws_port = int(solana_rpc_port) + 1
    secondary_solana_rpc_port = os.getenv('SECONDARY_SOLANA_RPC_PORT')
    secondary_solana_ws_port = int(secondary_solana_rpc_port) + 1
    solana_rpc_endpoint = f'localhost:{solana_rpc_port}'
    secondary_solana_rpc_endpoint = f'localhost:{secondary_solana_rpc_port}'

    # Generate keypair to use for publishing
    logging.debug('Generating keypair')
    cfg_dir = mkdtemp(prefix='cfg_')
    keypair_path = os.path.join(cfg_dir, 'id.json')
    logging.debug('Generated keypair path: %s', keypair_path)
    keygen_output = check_output([
        'solana-keygen', 'new', '--no-passphrase', '--outfile', keypair_path
    ]).decode('ascii').splitlines()
    pub_key = [line for line in keygen_output if 'pubkey' in line][0].split('pubkey: ')[1]
    logging.debug('Generated keypair')

    # Generate keypair for program, which will enable us to deploy to the same address on both networks
    logging.debug('Generating program keypair')
    program_keypair_path = os.path.join(cfg_dir, 'program_keypair.json')
    logging.debug('Generated program keypair path: %s', program_keypair_path)
    program_keygen_output = check_output([
        'solana-keygen', 'new', '--no-passphrase', '--outfile', program_keypair_path
    ]).decode('ascii').splitlines()
    logging.debug('Generated keypair')

    # ---------------------------------------- Primary Network ----------------------------------------
    # Start Solana Test Validator
    logging.debug('Setting up primary network')
    logging.debug('Starting Solana test validator')
    Popen([
        'solana-test-validator', '--rpc-port', str(solana_rpc_port), '--ledger', mkdtemp(prefix='stv_')], stdout=subprocess.DEVNULL)
    time.sleep(3)
    logging.debug('Started Solana test validator')

    # Airdrop some SOL to the publish key
    logging.debug('Airdropping SOL')
    check_call([
        'solana', 'airdrop', '100', pub_key,
        '--commitment', 'finalized',
        '--url', f'http://{solana_rpc_endpoint}',
        '--keypair', keypair_path,
    ])
    logging.debug('Airdropped SOL')

    # Deploy the program
    # TODO: need to get the keypair of the deployed program, or generate one first and give it to the command
    logging.debug('Deploying program')
    deploy_output = check_output([
        'solana', 'program', 'deploy',
        os.path.join(PYTH_CLIENT_PATH, 'target', 'oracle.so'),
        '--commitment', 'finalized',
        '--url', f'http://{solana_rpc_endpoint}',
        '--program-id', program_keypair_path,
        '--keypair', keypair_path,
    ]).decode('ascii').splitlines()
    program_key = [line for line in deploy_output if 'Program Id' in line][0].split('Program Id: ')[1]
    logging.debug('Deployed program')

    # Write program key to file
    logging.debug('Writing program key to file')
    pythd_dir = mkdtemp(prefix='pythd_')
    logging.debug('pythd temporary directory: %s', pythd_dir)
    with open(os.path.join(pythd_dir, 'program_key.json'), 'w') as f:
        f.write(program_key)

    # Create the publish_key_pair.json symlink
    logging.debug('Creating publish_key_pair.json symlink')
    path = os.path.join(pythd_dir, 'publish_key_pair.json')
    os.symlink(keypair_path, path)
    logging.debug('Created publish_key_pair.json symlink')

    # Init the mapping account
    logging.debug('Initializing mapping account')
    check_call([
        'pyth_admin', 'init_mapping',
        '-r', solana_rpc_endpoint,
        '-k', pythd_dir,
        '-c', 'finalized',
    ])
    logging.debug('Initialized mapping account')
    
    # Read the public key of the mapping account
    mapping_key = check_output([
        'solana-keygen', 'pubkey', pythd_dir+"/mapping_key_pair.json"
        ]).decode("utf-8").strip()
    logging.debug('Mapping account public key: ' + mapping_key)

    # Add the product accounts
    logging.debug('Adding product accounts')
    product_accounts = {
        product: check_output([
            'pyth_admin', 'add_product',
            '-r', solana_rpc_endpoint,
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
        '-r', solana_rpc_endpoint,
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
            '-r', solana_rpc_endpoint,
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
            '-r', solana_rpc_endpoint,
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
            '-r', solana_rpc_endpoint,
            '-k', pythd_dir,
            '-c', 'finalized',
            '-n',
        ])
    logging.debug('Initialized price accounts')

    # Python migration script:
    # - Need list of account pubkeys: mapping accounts, product accounts and price accounts.
    # - Use PythClient library to get these.
    # - Later, when we have the secondary network deployed:
    #   - For each account, create an account on the secondary network with the size and data of the account in the old network.
    #   - 
    all_accounts = await get_all_accounts(mapping_key, program_key, solana_rpc_endpoint, solana_ws_port)
    print(all_accounts)

    # ---------------------------------------- Secondary Network ----------------------------------------
    # TODO: script to migrate accounts from old network to new
    #       ^^^ This should keep the structure of the accounts the same.
    # Start Secondary Solana Test Validator
    logging.debug('Setting up secondary network')
    logging.debug('Secondary: Starting Solana test validator')
    if os.path.exists("secondary_solana_output.txt"):
        os.remove("secondary_solana_output.txt")
    with open("secondary_solana_output.txt", 'w') as f:
        Popen([
            'solana-test-validator', '--rpc-port', str(secondary_solana_rpc_port), '--ledger', mkdtemp(prefix='secondary_stv_'), '--faucet-port', '9915'],
            stdout=f)
        time.sleep(3)
        logging.debug('Secondary: Started Solana test validator')

    # Log the output of the secondary validator
    if os.path.exists("secondary_solana_logs.txt"):
        os.remove("secondary_solana_logs.txt")
    with open("secondary_solana_logs.txt", 'w') as f:
        cmd = [
            'solana', 'logs',
            '--commitment', 'finalized',
            '--url', f'http://localhost:{secondary_solana_rpc_port}',
            '--keypair', os.path.join(pythd_dir, 'publish_key_pair.json'),
        ]
        Popen(cmd, stdout=f)

    # Airdrop some SOL to the publish key
    logging.debug('Secondary: Airdropping SOL')
    check_call([
        'solana', 'airdrop', '1000', pub_key,
        '--commitment', 'finalized',
        '--url', f'http://localhost:{secondary_solana_rpc_port}',
        '--keypair', os.path.join(pythd_dir, 'publish_key_pair.json'),
    ])
    logging.debug('Secondary: Airdropped SOL')

    # Deploy the program
    logging.debug('Secondary: Deploying program')
    secondary_deploy_output = check_output([
        'solana', 'program', 'deploy',
        os.path.join(PYTH_CLIENT_PATH, 'target', 'oracle.so'),
        '--commitment', 'finalized',
        '--url', f'http://localhost:{secondary_solana_rpc_port}',
        '--keypair', keypair_path,
        '--program-id', program_keypair_path,
    ]).decode('ascii').splitlines()
    print(secondary_deploy_output)
    logging.debug('Secondary: Deployed program')

    # Connect to the primary instance, to pull data about the accounts
    solana_client = Client(f'http://localhost:{solana_rpc_port}')

    # Connect to the secondary instance, to create and initialize the accounts
    print("Secondary: creating accounts")
    secondary_solana_client = Client(f'http://localhost:{secondary_solana_rpc_port}')

    # Signing transactions:
    # Mapping accounts need to be signed from:
    # - The funding account
    # - The mapping account
    program_public_key = PublicKey(program_key)
    funding_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, 'publish_key_pair.json'))
    mapping_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, 'mapping_key_pair.json'))

    # Create an account
    for account in all_accounts:

        print(f"Creating account: {account}")
        account_info = solana_client.get_account_info(account.key)
        data = account_info['result']['value']['data'][0]
        data_bytes = base64.b64decode(data)

        # Determine which keypair this account should be associated with
        if isinstance(account, PythMappingAccount):
            account_keypair = mapping_solana_keypair
        else:
            account_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{account.key}.json'))

        # Create the transaction
        txn = Transaction().add(
            create_account(
                CreateAccountParams(
                    from_pubkey=funding_solana_keypair.public_key,
                    new_account_pubkey=account_keypair.public_key,
                    lamports=account.lamports,
                    space=len(data_bytes),
                    program_id=program_public_key
                )
            )
        )

        # Execute the transaction
        resp = secondary_solana_client.send_transaction(txn, funding_solana_keypair, account_keypair, opts=TxOpts(skip_preflight=True))
        print("Create account transaction response")
        print(resp)

    # Wait for new accounts to be
    time.sleep(50)

    # Transactions:
    # - init_mapping
    # - For each product:
    #   - Add product
    # - For each product
    #    - Update product
    # - For each price
    #   - Add price
    # - For each price
    #   - Permission publisher

    # Init the mapping account
    secondary_solana_client.send_transaction(Transaction().add(
        init_mapping_instruction(
            funding_solana_keypair.public_key,
            program_public_key,
            mapping_solana_keypair.public_key
        )
    ), funding_solana_keypair, mapping_solana_keypair, opts=TxOpts(skip_preflight=True))
    time.sleep(50)

    # Add all the products
    for product in PRODUCTS.keys():
        product_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{product_accounts[product]}.json'))
        secondary_solana_client.send_transaction(Transaction().add(
            add_product_instruction(
                funding_solana_keypair.public_key,
                program_public_key,
                mapping_solana_keypair.public_key,
                product_solana_keypair.public_key
            )
        ), funding_solana_keypair, mapping_solana_keypair, product_solana_keypair, opts=TxOpts(skip_preflight=True))
    time.sleep(50)

    # Update each product's metadata
    for product in PRODUCTS.keys():
        product_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{product_accounts[product]}.json'))
        secondary_solana_client.send_transaction(Transaction().add(
            update_product_instruction(
                funding_solana_keypair.public_key,
                program_public_key,
                product_solana_keypair.public_key,
                PRODUCTS[product]
            )
        ), funding_solana_keypair, product_solana_keypair, opts=TxOpts(skip_preflight=True))
    time.sleep(50)
    
    # Add all the price accounts
    for account in all_accounts:
        if not isinstance(account, PythPriceAccount):
            continue

        print("Adding price account")
            
        product_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{account.product_account_key}.json'))
        price_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{account.key}.json'))

        secondary_solana_client.send_transaction(Transaction().add(
            add_price_instruction(
                funding_solana_keypair.public_key,
                program_public_key,
                product_solana_keypair.public_key,
                price_solana_keypair.public_key,
                -5
            )
        ), funding_solana_keypair, product_solana_keypair, price_solana_keypair, opts=TxOpts(skip_preflight=True))
    time.sleep(50)

    # Permission the funding account to publish to all price accounts
    for account in all_accounts:
        if not isinstance(account, PythPriceAccount):
            continue

        price_solana_keypair = solana_keypair_from_file(os.path.join(pythd_dir, f'account_{account.key}.json'))

        secondary_solana_client.send_transaction(Transaction().add(
            permission_publisher(
                funding_solana_keypair.public_key,
                program_public_key,
                price_solana_keypair.public_key,
                funding_solana_keypair.public_key,
            )
        ), funding_solana_keypair, price_solana_keypair, opts=TxOpts(skip_preflight=True))
    time.sleep(50)

    # Sanity-check: fetch all accounts
    secondary_all_accounts = await get_all_accounts(mapping_key, program_key, secondary_solana_rpc_endpoint, secondary_solana_ws_port)
    print(secondary_all_accounts)

    # Create symlinks to the temporary keystore
    if os.path.exists(keystore_dir):
        os.remove(keystore_dir)
    os.symlink(pythd_dir, keystore_dir)

    logging.debug("done! sleeping forever...")
    while True: time.sleep(1000)

async def get_all_accounts(mapping_key, program_key, solana_rpc_endpoint, solana_ws_port):
    async with PythClient(
        first_mapping_account_key=mapping_key,
        program_key=program_key,
        solana_endpoint=f'http://{solana_rpc_endpoint}',
        solana_ws_endpoint=f'ws://localhost:{solana_ws_port}'
    ) as pyth_client:
        await pyth_client.refresh_all_prices()
        all_accounts = await pyth_client.get_all_accounts()
        return all_accounts

def solana_keypair_from_file(path):
    with open(path) as f:
        secret_key = bytes(json.loads(f.readlines()[0]))
        return Keypair.from_secret_key(secret_key=secret_key)

def init_mapping_instruction(funding_key, program_key, mapping_key):
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_INIT_MAPPING))
    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=mapping_key, is_signer=True, is_writable=True)
        ],
        program_id=program_key
    )

def add_product_instruction(funding_key, program_key, mapping_key, new_product_key):
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_ADD_PRODUCT))
    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=mapping_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=new_product_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key
    )

def update_product_instruction(funding_key, program_key, product_key, product_metadata):
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_UPD_PRODUCT))
    data_extra = encode_product_metadata(product_metadata)
    return TransactionInstruction(
        data=data + data_extra,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key
    )

def add_price_instruction(
    funding_key: PublicKey,
    program_key: PublicKey,
    product_key: PublicKey,
    new_price_key: PublicKey,
    exponent: int,
    price_type: int = PRICE_TYPE_PRICE,
) -> TransactionInstruction:
    """
    Pyth program add_price instruction
    accounts:
    - funding account (signer, writable)
    - product account (signer, writable)
    - new price account (signer, writable)
    """
    layout = Struct(
        "version" / Int32ul, "command" / Int32sl, "exponent" / Int32sl, "type" / Int32ul
    )
    data = layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=COMMAND_ADD_PRICE,
            exponent=exponent,
            type=price_type,
        )
    )

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=new_price_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )

def permission_publisher(
    funding_key: PublicKey,
    program_key: PublicKey,
    price_account_key: PublicKey,
    publisher_key: PublicKey,
) -> TransactionInstruction:
    """
    Pyth program add_publisher instruction
    accounts:
    - funding account (signer, writable)
    - price account (signer, writable)
    """
    layout = Struct(
        "version" / Int32ul, "command" / Int32sl, "publisher_key" / Bytes(32)
    )
    data = layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=COMMAND_ADD_PUBLISHER,
            publisher_key=bytes(publisher_key),
        )
    )

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=price_account_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )

def encode_product_metadata(data: Dict[str, str]) -> bytes:
    buffer = b""

    for key, value in data.items():
        key_bytes = key.encode("utf8")
        key_len = len(key_bytes).to_bytes(1, byteorder="little")
        value_bytes = value.encode("utf8")
        value_len = len(value_bytes).to_bytes(1, byteorder="little")

        buffer += key_len + key_bytes + value_len + value_bytes

    return buffer


if __name__ == '__main__':
    asyncio.run(main())
