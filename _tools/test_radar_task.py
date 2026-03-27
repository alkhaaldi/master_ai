import sys, os, asyncio, logging
sys.path.insert(0, "/var/lib/homeassistant/share/master_ai")
os.chdir("/var/lib/homeassistant/share/master_ai")

# Add venv packages
venv_path = "/home/pi/master_ai/venv/lib/python3.13/site-packages"
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

logging.basicConfig(level=logging.DEBUG)

async def test():
    from stock_radar import radar_loop

    async def fake_sender(text):
        print(f"[WOULD SEND TG]: {text[:100]}")

    print("=== Creating radar_loop task ===")
    task = asyncio.create_task(radar_loop(fake_sender))

    # Add done callback to catch exceptions
    def on_done(t):
        if t.cancelled():
            print("TASK CANCELLED!")
        elif t.exception():
            print(f"TASK EXCEPTION: {t.exception()}")
            import traceback
            traceback.print_exception(type(t.exception()), t.exception(), t.exception().__traceback__)
        else:
            print("TASK FINISHED OK")

    task.add_done_callback(on_done)

    # Wait a few seconds to see if task starts or crashes
    print("Waiting 10 seconds for task to start...")
    await asyncio.sleep(10)
    print(f"Task done: {task.done()}, cancelled: {task.cancelled()}")
    if task.done() and task.exception():
        print(f"Exception: {task.exception()}")
    task.cancel()

asyncio.run(test())
