# Tenant-zone key custody

**A lost key is not a deleted tenant, and nothing here may report one as the other.**
Ciphertext nobody holds a key for is unreadable whatever the reason; operationally
the two causes want opposite responses (restore the key and page someone, versus
nothing, the account is gone). So backup and destruction are different acts on
different objects.

```
 $MTGC_LAKE_MASTER_KEY_FILE   one master key, mode 600     (never MTGC_MASTER_KEY: that is the BYO Anthropic key's)
        | HKDF-SHA256(salt = "mtgc-lake-tenant-key/v1", info = database_id)
        v
 per-tenant lake key          derived, never stored
        ^
        | refused when ...
 registry.sqlite: lake_tenant_key(database_id -> active | tombstoned)
```

Code: `mtg_collector/lake/crypto.py` (HKDF, AES-256-GCM envelope, aad = the object's
key, so a part moved to another tenant or path fails to open), `lake/keys.py`
(state; the only door to a key), `lake/resolve.py` (key layout and the resolution
rule). The shipper, read-back and eraser import these and nothing else.

| | backup | destruction |
|---|---|---|
| object | the master key file | one row in `lake_tenant_key` |
| verb | `mtg tenant lake-key backup --yes` | `mtg tenant lake-key tombstone ID --reason R --yes` |
| scope | every tenant | exactly one database_id |
| reach | never opens the registry | never opens the key file |

`lake.keys.lake_key` consults the state **before** the master, so a tombstoned
tenant is refused whether or not the master is present, and only `KeyTombstoned`
has `deliberate_revocation` true. An id with no row is refused (absence is not
permission: a registry restored empty is loud). A tombstone is terminal in the
schema (triggers refuse update and delete), and `purge_tenant` writes one.
A tombstone stops our code deriving the key; the real erasure is the prefix drop.

## Minting and backing up (Ryan)

```bash
export MTGC_LAKE_MASTER_KEY_FILE=~/.config/mtgc/<inst>/tenant-master.key   # dir mode 700
mtg tenant lake-key init        # refuses to overwrite; prints a fingerprint
mtg tenant lake-key backup --yes   # paste into the password manager
mtg tenant lake-key register --all
mtg tenant lake-key status
```

**Ryan backs up the master key.** It is deliberately not replicated to S3: a key
stored beside its ciphertext protects nothing. The fingerprint printed by `init`
is how you later confirm the stored copy is the box's key.

Nothing on the box can check that the key was backed up. Do not arm the shipper
until it has been.
