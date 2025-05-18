from models import *

from tronpy import Tron
from tronpy.abi import trx_abi
from tronpy.providers import HTTPProvider
from tronpy.exceptions import BlockNotFound
import requests ,schedule , time ,datetime

BASE_URL = "http://nginx"
BLOCKCHAIN_ID = "TRON"
CURRENCY_TRON_ID = "Tron"
CURRENCY_USDT_ID = "Tether"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

memory_cache = {

    "last_block" : None,
    "transactions" : [],
    "current_block" : last_block_id(),
    
    "last_update_wallet_list" : None,
    "last_update_transaction_list" : None,
}

API_KEY = "a374813c-9345-4e63-93e6-c47a2481f80d"

block_client = Tron(HTTPProvider(api_key = API_KEY))
transaction_client = Tron(HTTPProvider(api_key = API_KEY))

class TrxTransaction:
    def __init__(self, hash, from_addr, to_addr, value, contract_address=None, is_success=False):
        self._hash = hash
        self._from_addr = from_addr
        self._to_addr = to_addr
        self._value = value
        self._contract_address = contract_address
        self._is_success = is_success

    @property
    def hash(self):
        return self._hash

    @property
    def from_addr(self):
        return self._from_addr

    @property
    def to_addr(self):
        return self._to_addr

    @property
    def value(self):
        return self._value

    @property
    def contract_address(self):
        return self._contract_address

    @property
    def is_success(self):
        return self._is_success

    @classmethod
    def from_node(cls, tx_data):
        hash = tx_data.get('txID')
        data = tx_data.get('raw_data', {})
        contract_address = None
        to_address = None
        from_address = None
        amount = 0

        contract = data.get('contract', [{}])[0]
        if contract.get('type') == 'TransferContract':
            value = contract.get('parameter', {}).get('value', {})
            amount = value.get('amount', 0)
            from_address = value.get('owner_address')
            to_address = value.get('to_address')

        elif contract.get('type') == 'TriggerSmartContract':
            value = contract.get('parameter', {}).get('value', {})
            contract_data = value.get('data')
            if contract_data:
                from_address = value.get('owner_address')
                contract_address = value.get('contract_address')
                if contract_data.startswith('a9059cbb'):
                    contract_fn_arguments = bytes.fromhex('00' * 12 + contract_data[32:])
                    try:
                        to_address, amount = trx_abi.decode(['address', 'uint256'], contract_fn_arguments)
                    except:
                        pass

        is_success = tx_data.get('ret', [{}])[0].get('contractRet') == 'SUCCESS'

        if hash and to_address:
            return cls(hash, from_address, to_address, amount, contract_address, is_success)

        return None


def update_transactions_list(transactions):
    
    if not transactions:
        return
    
    url = BASE_URL + "/transactions/"
    try:
        response = requests.post(url = url, json = transactions)
    except :
        return False
    
    if response.status_code == 200:
        return True
    
    return False
        

def update_wallets_list():
    print("[~] UPDATE WALLETS LIST.")
    def fetch_wallets_address(created_at = None):
        wallets = []
        page = 1
        
        while True:
            url = BASE_URL + "/wallets/addresses"
            params = {
                "page": page,
                "createdAt": created_at,
                "blockchainId": BLOCKCHAIN_ID,
            }
            
            response = requests.get(url, params=params)

            if response.status_code != 200:
                break
            
            data = response.json()

            if not data.get("result"): break  
            
            page += 1
            wallets.extend(data.get("result" ,[]))
        
        return wallets
    last_created_at = last_wallet_created_at()
    
    wallets = fetch_wallets_address(last_created_at)

    if not wallets:
        return 
    
    add_wallets_address([{"address": w["address"], "created_at": w["createdAt"]} for w in wallets])
    
    update_or_create_metadata(
        block_id = last_block_id(), wallet_date = max(w["createdAt"] for w in wallets))

   
def proccess_block_transactions():
    if not memory_cache["current_block"] or not memory_cache["last_block"]:
        block_id = block_client.get_latest_block_number()
        
        if not memory_cache["current_block"]:
            memory_cache["current_block"] = block_id - 10
        
        if not memory_cache["last_block"]:
            memory_cache["last_block"] = block_id 

        elif memory_cache["last_block"] and block_id > memory_cache["last_block"]:
            memory_cache["last_block"] = block_id 

        
        return update_or_create_metadata(memory_cache["current_block"],last_wallet_created_at())
    
    if memory_cache["current_block"] >= memory_cache["last_block"]:
        return
    
    if not memory_cache.get("last_update_wallet_list") or (
        datetime.datetime.now() - memory_cache["last_update_wallet_list"]).total_seconds() >= 60:

        update_wallets_list()
        memory_cache["last_update_wallet_list"] = datetime.datetime.now()


    addresses = get_all_wallet_addresses()

    while True:
        block_id = memory_cache["current_block"]

        try:
            block = block_client.get_block(block_id)
        except BlockNotFound:
            return
        except Exception :
            return update_or_create_metadata(block_id ,last_wallet_created_at())
        
        transactions = block.get('transactions', [])
        
        print(f"[~] FETCH ALL TRANSACTION BLOCK : {block_id} ,TOTAL TRANSACTION : {len(transactions)}")
        
        for transaction in transactions:
            tx: TrxTransaction = TrxTransaction.from_node(transaction)
            
            if tx is None or not tx.is_success:
                continue

            if tx.to_addr in addresses:
                transaction_dict = {
                    "block" : block_id ,
                    "to" : tx.to_addr,
                    "from" : tx.from_addr,
                    "amount" : tx.value / 1_000_000
                }
                if transaction_dict["amount"] <= 1:
                    continue

                if not tx.contract_address:
                    print(f"[~] TRX Deposit : {transaction_dict['amount']}")
                    transaction_dict["currencyId"] = CURRENCY_TRON_ID
                    memory_cache["transactions"].append(transaction_dict)
                elif tx.contract_address == USDT_CONTRACT:
                    print(f"[~] USDT Deposit : {transaction_dict['amount']}")
                    transaction_dict["currencyId"] = CURRENCY_USDT_ID
                    memory_cache["transactions"].append(transaction_dict)
 
        if memory_cache["transactions"]:
            if not memory_cache.get("last_update_transaction_list") or (
                datetime.datetime.now() - memory_cache["last_update_transaction_list"]).total_seconds() >= 60:
                print("[~] SYNC TRANSACTION TO SERVER")
                if update_transactions_list(memory_cache["transactions"]):
                    memory_cache["transactions"] = []
                
                update_or_create_metadata(
                    memory_cache["current_block"] ,last_wallet_created_at())

                memory_cache["last_update_transaction_list"] = datetime.datetime.now()

        if memory_cache["current_block"] + 1 <= memory_cache["last_block"]:
            memory_cache["current_block"] += 1
        else :
            break

    return update_or_create_metadata(
        memory_cache["current_block"] ,last_wallet_created_at())

schedule.every(10).seconds.do(proccess_block_transactions)


while True:
    schedule.run_pending()
    time.sleep(1)
