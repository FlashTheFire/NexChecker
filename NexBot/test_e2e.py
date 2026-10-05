"""Test NexNum JSON Junction responses."""
import asyncio, sys
sys.path.insert(0, ".")
from core.nexnum_api import nexnum_client

API_KEY = "nxn_live_834pV7wW1kimHGG2yuPD3G3c9G2Ll9LK"

async def main():
    print("=== JSON Junction Test ===\n")

    # 1. Balance
    bal = await nexnum_client.get_balance(API_KEY)
    print(f"getBalance  ok={bal['ok']}  balance={bal['balance']}  error={bal['error']}")

    # 2. Buy number
    print("getNumber ...")
    buy = await nexnum_client.get_number(API_KEY, "nl", "22")
    print(f"  ok       = {buy['ok']}")
    print(f"  status   = {buy.get('status')}")
    print(f"  order_id = {buy.get('order_id')}")
    print(f"  number   = {buy.get('number')}")

    if buy["ok"]:
        oid = buy["order_id"]

        # 3. Status poll
        st = await nexnum_client.get_status(API_KEY, oid)
        print(f"\ngetStatus   ok={st['ok']}  status={st['status']}  code={st['code']!r}")

        # 4. Cancel
        cr = await nexnum_client.set_status(API_KEY, oid, 8)
        print(f"setStatus8  ok={cr['ok']}  status={cr['status']}")

    await nexnum_client.close()
    print("\n=== Done ===")

if __name__ == "__main__":
    asyncio.run(main())
