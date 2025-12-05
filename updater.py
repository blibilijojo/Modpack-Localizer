import sys
import os
import time
import subprocess
import psutil
def main():
    try:
        pid_to_wait_for = int(sys.argv[1])
        current_exe_path = sys.argv[2]
        new_exe_path = sys.argv[3]
        old_exe_backup_path = sys.argv[4]
        try:
            main_process = psutil.Process(pid_to_wait_for)
            main_process.wait(timeout=10)
        except psutil.NoSuchProcess:
            pass
        except (psutil.TimeoutExpired, Exception):
            try:
                main_process.kill()
            except psutil.NoSuchProcess:
                pass
        time.sleep(1)
        os.rename(current_exe_path, old_exe_backup_path)
        os.rename(new_exe_path, current_exe_path)
        subprocess.Popen([current_exe_path])
        subprocess.Popen(
            f'ping 127.0.0.1 -n 2 > nul & del "{sys.executable}"',
            shell=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        with open("updater_error.log", "w", encoding='utf-8') as f:
            f.write(f"An error occurred during update: {e}\n")
            f.write(f"Arguments: {sys.argv}\n")
if __name__ == '__main__':
    main()