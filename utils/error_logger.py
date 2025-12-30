import logging
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

LOG_DIR = Path("error_logs")
AI_ERROR_LOG_DIR = LOG_DIR / "ai"
GENERAL_ERROR_LOG_DIR = LOG_DIR / "general"
MAX_LOG_DAYS = 10

class ErrorLogger:
    @staticmethod
    def _ensure_log_dirs():
        AI_ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
        GENERAL_ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    @staticmethod
    def _clean_old_logs():
        """清理超过指定天数的旧日志文件"""
        cutoff_date = datetime.now() - timedelta(days=MAX_LOG_DAYS)
        for log_dir in [AI_ERROR_LOG_DIR, GENERAL_ERROR_LOG_DIR]:
            if log_dir.exists():
                for log_file in log_dir.iterdir():
                    if log_file.is_file():
                        file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                        if file_time < cutoff_date:
                            try:
                                log_file.unlink()
                                logging.debug(f"已清理旧日志文件: {log_file}")
                            except Exception as e:
                                logging.warning(f"清理旧日志文件失败: {log_file} - {e}")
    @staticmethod
    def log_ai_error(prompt: str, response_text: str, error_type: str = "format_error"):
        """
        在一个独立的、带时间戳的文件中，记录一次AI返回错误。
        Args:
            prompt: 发送给AI的完整请求内容。
            response_text: AI返回的原始、有问题的文本。
            error_type: 错误类型，如format_error、timeout_error、rate_limit_error等。
        """
        try:
            ErrorLogger._ensure_log_dirs()
            ErrorLogger._clean_old_logs()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_file_path = AI_ERROR_LOG_DIR / f"ai_{error_type}_{timestamp}.log"
            log_content = f"""# AI Response Error Log
# Timestamp: {datetime.now().isoformat()}
# Error Type: {error_type}
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
            logging.error(f"AI响应{error_type}错误！已将详细请求和回复保存到快照日志: {log_file_path.name}")
        except Exception as e:
            logging.error(f"写入AI错误快照日志时发生异常: {e}")
    @staticmethod
    def log_general_error(error_title: str, error_message: str, exception: Optional[Exception] = None, 
                         context: Optional[Dict[str, Any]] = None, error_level: str = "ERROR"):
        """
        记录一般错误信息到文件。
        Args:
            error_title: 错误标题。
            error_message: 错误详细信息。
            exception: 异常对象（可选）。
            context: 错误上下文信息（可选）。
            error_level: 错误级别，如DEBUG、INFO、WARNING、ERROR、CRITICAL。
        """
        try:
            ErrorLogger._ensure_log_dirs()
            ErrorLogger._clean_old_logs()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_file_path = GENERAL_ERROR_LOG_DIR / f"general_{error_level.lower()}_{timestamp}.log"
            
            log_content = [
                f"# General Error Log",
                f"# Timestamp: {datetime.now().isoformat()}",
                f"# Error Level: {error_level}",
                f"# Error Title: {error_title}",
                f"# --------------------------------------------------",
                f"### ERROR MESSAGE ###",
                f"# --------------------------------------------------",
                f"{error_message}"
            ]
            
            if exception:
                log_content.extend([
                    f"# --------------------------------------------------",
                    f"### EXCEPTION DETAILS ###",
                    f"# --------------------------------------------------",
                    f"Type: {type(exception).__name__}",
                    f"Message: {str(exception)}",
                    f"# --------------------------------------------------",
                    f"### TRACEBACK ###",
                    f"# --------------------------------------------------",
                    f"{traceback.format_exc()}"
                ])
            
            if context:
                log_content.extend([
                    f"# --------------------------------------------------",
                    f"### CONTEXT INFORMATION ###",
                    f"# --------------------------------------------------"
                ])
                for key, value in context.items():
                    log_content.append(f"{key}: {value}")
            
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_content))
            
            # 根据错误级别记录到日志
            log_func = getattr(logging, error_level.lower())
            log_func(f"{error_title}: {error_message} (详细日志已保存到: {log_file_path.name})")
        except Exception as e:
            logging.error(f"写入一般错误日志时发生异常: {e}")
    @staticmethod
    def get_error_summary(error_type: str = None) -> str:
        """
        获取错误日志摘要。
        Args:
            error_type: 错误类型（可选）。
        Returns:
            错误日志摘要字符串。
        """
        summary = []
        ErrorLogger._ensure_log_dirs()
        
        if error_type == "ai" or error_type is None:
            ai_logs = sorted(AI_ERROR_LOG_DIR.iterdir(), reverse=True)
            summary.append(f"AI错误日志数量: {len(ai_logs)}")
            if ai_logs:
                recent_logs = ai_logs[:5]  # 显示最近5个日志
                summary.append("最近的AI错误日志:")
                for log in recent_logs:
                    summary.append(f"  - {log.name}")
        
        if error_type == "general" or error_type is None:
            general_logs = sorted(GENERAL_ERROR_LOG_DIR.iterdir(), reverse=True)
            summary.append(f"一般错误日志数量: {len(general_logs)}")
            if general_logs:
                recent_logs = general_logs[:5]  # 显示最近5个日志
                summary.append("最近的一般错误日志:")
                for log in recent_logs:
                    summary.append(f"  - {log.name}")
        
        return '\n'.join(summary)

def log_ai_error(prompt: str, response_text: str):
    """
    兼容旧版API的包装函数
    """
    ErrorLogger.log_ai_error(prompt, response_text)