from __future__ import annotations
import logging
import threading
import openai


class StreamManager:
    """管理 AI API 的流式请求连接。"""

    def __init__(self):
        self._active_stream_lock = threading.Lock()
        self._active_streams: list = []

    def register(self, stream) -> None:
        with self._active_stream_lock:
            self._active_streams.append(stream)

    def unregister(self, stream) -> None:
        with self._active_stream_lock:
            try:
                self._active_streams.remove(stream)
            except ValueError:
                pass

    def close_all(self) -> None:
        with self._active_stream_lock:
            streams = tuple(self._active_streams)
            self._active_streams.clear()
        for s in streams:
            try:
                s.close()
            except Exception as e:
                logging.debug(f"关闭进行中请求流: {e}")

    def consume_sync(self, client: openai.OpenAI, request_params: dict, cancelled_check) -> str | None:
        params = dict(request_params)
        params["stream"] = True
        stream = client.chat.completions.create(**params)
        self.register(stream)
        parts: list[str] = []
        try:
            try:
                for chunk in stream:
                    if cancelled_check():
                        return None
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is not None and delta.content:
                        parts.append(delta.content)
            except Exception:
                if cancelled_check():
                    return None
                raise
            return "".join(parts)
        finally:
            self.unregister(stream)
            try:
                stream.close()
            except Exception:
                pass

    async def consume_async(self, client: openai.AsyncOpenAI, request_params: dict, cancelled_check) -> str | None:
        params = dict(request_params)
        params["stream"] = True
        stream = await client.chat.completions.create(**params)
        self.register(stream)
        parts: list[str] = []
        try:
            try:
                async for chunk in stream:
                    if cancelled_check():
                        return None
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is not None and delta.content:
                        parts.append(delta.content)
            except Exception:
                if cancelled_check():
                    return None
                raise
            return "".join(parts)
        finally:
            self.unregister(stream)
            try:
                await stream.close()
            except Exception:
                pass
