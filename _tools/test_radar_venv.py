import sys, os, asyncio, logging
sys.path.insert(0, "/var/lib/homeassistant/share/master_ai")
os.chdir("/var/lib/homeassistant/share/master_ai")

# Activate venv packages
venv_path = "/home/pi/master_ai/venv/lib/python3.13/site-packages"
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

logging.basicConfig(level=logging.DEBUG)

async def test():
    print(f"Python: {sys.executable}")
    print(f"sys.path has venv: {any('venv' in p for p in sys.path)}")
    
    # Test tvDatafeed import
    try:
        from tvDatafeed import TvDatafeed, Interval
        print("tvDatafeed imported OK!")
    except Exception as e:
        print(f"tvDatafeed import FAILED: {e}")
        return
    
    # Test actual data fetch
    try:
        tv = TvDatafeed()
        print("TvDatafeed() created")
        df = tv.get_hist("KFH", "KSE", Interval.in_30_minute, n_bars=5)
        if df is not None and not df.empty:
            print(f"KFH data: {len(df)} bars")
            print(f"  last: {df.index[-1]} close={df.iloc[-1]['close']}")
        else:
            print("KFH: NO DATA returned")
    except Exception as e:
        print(f"KFH fetch ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Now test radar check_symbol with venv
    print("\n=== Testing check_symbol ===")
    try:
        from stock_radar import check_symbol
        result = check_symbol("KFH")
        if result.get("error"):
            print(f"check_symbol ERROR: {result['error']}")
        else:
            print(f"check_symbol OK: signal={result.get('signal')} price={result.get('price')} score={result.get('score')}")
    except Exception as e:
        print(f"check_symbol EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
