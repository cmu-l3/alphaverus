import os
import time
from pathlib import Path

def check_and_remove_lock_files():
    # File paths
    exp_lock = "experiment_state.json.lock"
    exp_over_lock = "experiment_state_over.json.lock"
    
    # Time thresholds in seconds
    THIRTY_MINUTES = 30 * 60
    TWO_HOURS = 120 * 60
    current_time = time.time()

    # Check experiment_state.json.lock
    if os.path.exists(exp_lock) and not os.path.exists(exp_over_lock):
        file_time = os.path.getmtime(exp_lock)
        print(f"File time: {file_time}")
        if (current_time - file_time) > THIRTY_MINUTES:
            try:
                os.remove(exp_lock)
                print(f"Deleted {exp_lock} - file was older than 30 minutes")
            except Exception as e:
                print(f"Error deleting {exp_lock}: {e}")

    # Check experiment_state_over.json.lock
    if os.path.exists(exp_over_lock):
        file_time = os.path.getmtime(exp_over_lock)
        if (current_time - file_time) > TWO_HOURS:
            try:
                os.remove(exp_over_lock)
                print(f"Deleted {exp_over_lock} - file was older than 120 minutes")
                os.remove(exp_lock)
                print(f"Deleted {exp_lock} - file was older than 120 minutes")
            except Exception as e:
                print(f"Error deleting {exp_over_lock}: {e}")

if __name__ == "__main__":
    while True:
        check_and_remove_lock_files() 
        time.sleep(60)