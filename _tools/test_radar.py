import sys, os, asyncio, logging
os.chdir("/var/lib/homeassistant/share/master_ai")
sys.path.insert(0, ".")
logging.basicConfig(level=logging.DEBUG)

async def test():
    print("=== Testing radar_loop init ===")
    try:
        from stock_radar import radar_loop, init_radar_db, _get_config, check_symbol, get_watchlist
        print("imports OK")
    except Exception as e:
        print(f"IMPORT ERROR: {e}")
        return

    try:
        init_radar_db()
        print("init_radar_db OK")
    except Exception as e:
        print(f"init_radar_db ERROR: {e}")

    cfg = _get_config()
    print(f"config: enabled={cfg.get('enabled')}")

    try:
        from tv_data import _is_market_open
        print(f"market_open: {_is_market_open()}")
    except Exception as e:
        print(f"market check ERROR: {e}")

    # Try checking one symbol manually
    print("\n=== Manual check_symbol test ===")
    try:
        result = check_symbol("KFH")
        print(f"KFH result: {result}")
    except Exception as e:
        print(f"check_symbol ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
