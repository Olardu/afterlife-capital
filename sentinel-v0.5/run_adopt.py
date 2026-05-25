"""Wrapper: runs adopt_orphan_positions and writes output to a log file."""
import sys
import os

# Redirect stdout/stderr to file
log_path = os.path.join(os.path.dirname(__file__), 'adopt_orphan_output.log')
log = open(log_path, 'w', encoding='utf-8')
sys.stdout = log
sys.stderr = log

try:
    # Change to script directory for .env loading
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Import and run
    from adopt_orphan_positions import main
    import asyncio
    
    # Check args
    apply = '--apply' in sys.argv
    asyncio.run(main(apply=apply))
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", file=log)
    import traceback
    traceback.print_exc(file=log)
finally:
    log.flush()
    log.close()
