import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any
class DictionarySearcher:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path) if db_path else None
        self.conn = None
        if self.db_path and self.db_path.exists():
            try:
                self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA query_only = ON;")
            except sqlite3.Error as e:
                logging.error(f"无法以只读模式连接到词典数据库: {self.db_path}. 错误: {e}")
                self.conn = None
        elif not self.db_path:
            logging.warning("词典路径未配置，查询功能将不可用。")
        else:
            logging.warning(f"提供的词典路径不存在: {self.db_path}，查询功能将不可用。")
    def is_available(self) -> bool:
        return self.conn is not None
    def _execute_query(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        results = []
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"执行词典查询时发生致命错误: {e}", exc_info=True)
        return []
    def search_by_english(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not query.strip(): return []
        search_term = f"%{query.strip()}%"
        sql = """
        SELECT KEY, ORIGIN_NAME, TRANS_NAME, VERSION
        FROM dict
        WHERE ORIGIN_NAME LIKE ? OR KEY LIKE ?
        ORDER BY
            CASE WHEN ORIGIN_NAME = ? THEN 0 ELSE 1 END,
            CASE WHEN KEY = ? THEN 2 ELSE 3 END,
            CASE WHEN ORIGIN_NAME LIKE ? THEN 4 ELSE 5 END,
            LENGTH(ORIGIN_NAME)
        LIMIT ?
        """
        params = (search_term, search_term, query, query, f"{query}%", limit)
        return self._execute_query(sql, params)
    def search_by_chinese(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not query.strip(): return []
        search_term = f"%{query.strip()}%"
        sql = """
        SELECT KEY, ORIGIN_NAME, TRANS_NAME, VERSION
        FROM dict
        WHERE TRANS_NAME LIKE ?
        ORDER BY
            CASE WHEN TRANS_NAME = ? THEN 0 ELSE 1 END,
            CASE WHEN TRANS_NAME LIKE ? THEN 2 ELSE 3 END,
            LENGTH(TRANS_NAME)
        LIMIT ?
        """
        params = (search_term, query, f"{query}%", limit)
        return self._execute_query(sql, params)
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None