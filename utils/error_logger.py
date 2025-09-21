import logging
from pathlib import Path
from datetime import datetime
LOG_DIR = Path("ai_error_logs")
def log_ai_error(prompt: str, response_text: str):
    """
    在一个独立的、带时间戳的文件中，记录一次AI返回格式错误。
    Args:
        prompt: 发送给AI的完整请求内容。
        response_text: AI返回的原始、有问题的文本。
    """
    try:
        LOG_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_file_path = LOG_DIR / f"ai_error_{timestamp}.log"
        log_content = f"""# AI Response Error Log
# Timestamp: {datetime.now().isoformat()}
# --------------------------------------------------
### PROMPT SENT TO AI ###
# --------------------------------------------------
{prompt}
# --------------------------------------------------
### RAW RESPONSE FROM AI ###
# --------------------------------------------------
{response_text}
"""
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write(log_content)
        logging.error(f"AI响应格式错误！已将详细请求和回复保存到快照日志: {log_file_path}")
    except Exception as e:
        logging.error(f"写入AI错误快照日志时发生异常: {e}")