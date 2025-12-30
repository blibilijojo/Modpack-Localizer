# updater.py
# 这是一个独立的、极简的更新程序，它唯一的职责是替换文件并重启主程序。

import sys
import os
import time
import subprocess
import psutil  # 这是一个必要的第三方库

def main():
    try:
        # 从命令行参数获取所有需要的信息
        # sys.argv[0] 是脚本本身的名字
        pid_to_wait_for = int(sys.argv[1])
        current_exe_path = sys.argv[2]
        new_exe_path = sys.argv[3]
        old_exe_backup_path = sys.argv[4]

        # 1. 等待主程序进程退出
        # psutil 是一个跨平台的库，用于可靠地处理进程信息
        try:
            main_process = psutil.Process(pid_to_wait_for)
            # 等待最多10秒，防止无限等待
            main_process.wait(timeout=10)
        except psutil.NoSuchProcess:
            # 如果进程已经不存在，说明主程序已成功退出，这是最好的情况
            pass
        except (psutil.TimeoutExpired, Exception):
            # 如果等待超时或发生其他异常，为确保万无一失，尝试强制终止
            # 这种情况很少发生，但能极大增加更新的健壮性
            try:
                main_process.kill()
            except psutil.NoSuchProcess:
                pass  # 已经被杀死了，正好

        # 额外等待一秒，确保操作系统完全释放了对可执行文件的锁定
        time.sleep(1)

        # 2. 执行核心的文件替换操作
        os.rename(current_exe_path, old_exe_backup_path)
        os.rename(new_exe_path, current_exe_path)

        # 3. 重新启动新版本的应用程序
        # 使用 Popen 启动新进程，这样它不会阻塞更新器自身的退出
        subprocess.Popen([current_exe_path])

        # 4. 实现自我删除 (Windows上的经典技巧)
        # 启动一个新的 cmd.exe 进程，让它在1秒后删除 updater.exe 自身，然后退出
        # 此时，这个 updater.py 脚本已经完成了它的全部使命，可以安全退出了
        # DETACHED_PROCESS 确保它独立于 updater 进程运行
        subprocess.Popen(
            f'ping 127.0.0.1 -n 2 > nul & del "{sys.executable}"',
            shell=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        )

    except Exception as e:
        # 如果更新过程中的任何环节出错，创建一个日志文件以帮助调试
        with open("updater_error.log", "w", encoding='utf-8') as f:
            f.write(f"An error occurred during update: {e}\n")
            f.write(f"Arguments: {sys.argv}\n")

if __name__ == '__main__':
    main()