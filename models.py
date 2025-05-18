
from peewee import Model, CharField, DateTimeField, IntegerField, SqliteDatabase

db = SqliteDatabase('tron_wallets.db')

class Wallet(Model):
    address = CharField(unique=True) 
    created_at = DateTimeField() 

    class Meta:
        database = db

class Metadata(Model):
    last_checked_block_id = IntegerField(null = True) 
    last_wallet_created_at = DateTimeField()

    class Meta:
        database = db

def update_or_create_metadata(block_id, wallet_date):
    metadata, created = Metadata.get_or_create(id=1, defaults={
        'last_checked_block_id': block_id,
        'last_wallet_created_at': wallet_date
    })
    if not created:
        metadata.last_checked_block_id = block_id
        metadata.last_wallet_created_at = wallet_date
        metadata.save()
    return metadata

def last_block_id():
    metadata = Metadata.get_or_none(id = 1)
    return metadata.last_checked_block_id if metadata else None

def last_wallet_created_at():
    metadata = Metadata.get_or_none(id = 1)
    return metadata.last_wallet_created_at if metadata else "2025-01-01T00:00:00.00000Z"

def get_all_wallets():
    return list(Wallet.select())
def get_all_wallet_addresses():
    return [wallet.address for wallet in Wallet.select()]


def add_wallet_address(address ,created_date):
    wallet = Wallet.create(address=address, created_at=created_date)
    return wallet

def add_wallets_address(wallets_data):
    with db.atomic():
        Wallet.insert_many(wallets_data).execute()



db.connect()
db.create_tables([Wallet, Metadata])
