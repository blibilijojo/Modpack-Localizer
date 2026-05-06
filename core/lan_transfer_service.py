"""局域网传输服务 - UDP设备发现 + HTTP文件传输。"""

from __future__ import annotations

import json
import logging
import re
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, unquote

from core.save_format_adapter import get_device_name

PROTOCOL_MAGIC = "MODPACK_LOCALIZER"
UDP_PORT = 19871
HTTP_PORT_START = 19872
HTTP_PORT_END = 19882
BROADCAST_INTERVAL = 1.0
BROADCAST_COUNT = 15


class DeviceInfo:
    def __init__(self, name: str, http_port: int, platform: str, ip: str):
        self.name = name
        self.http_port = http_port
        self.platform = platform
        self.ip = ip

    def __repr__(self):
        return f"<Device {self.name} ({self.platform}) @ {self.ip}:{self.http_port}>"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "http_port": self.http_port,
            "platform": self.platform,
            "ip": self.ip,
        }


class LANTransferService:
    """局域网传输服务，支持设备发现和项目浏览/下载。"""

    def __init__(self):
        self.device_name = get_device_name()
        self.http_port: Optional[int] = None
        self._http_server: Optional[HTTPServer] = None
        self._udp_socket: Optional[socket.socket] = None
        self._running = False
        self._threads: List[threading.Thread] = []
        self._local_ips: List[str] = []

        self._on_device_found: Optional[Callable[[DeviceInfo], None]] = None
        self._on_file_received: Optional[Callable[[dict, str], None]] = None
        self._project_list_provider: Optional[Callable[[], List[dict]]] = None
        self._project_data_provider: Optional[Callable[[str], Optional[dict]]] = None

    def _collect_local_ips(self):
        self._local_ips.clear()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip not in self._local_ips:
                    self._local_ips.append(ip)
        except Exception:
            pass
        if "127.0.0.1" not in self._local_ips:
            self._local_ips.append("127.0.0.1")

    def _is_local_ip(self, ip: str) -> bool:
        return ip in self._local_ips

    def set_device_found_callback(self, callback: Callable[[DeviceInfo], None]):
        self._on_device_found = callback

    def set_file_received_callback(self, callback: Callable[[dict, str], None]):
        self._on_file_received = callback

    def set_project_providers(
        self,
        list_provider: Callable[[], List[dict]],
        data_provider: Callable[[str], Optional[dict]],
    ):
        self._project_list_provider = list_provider
        self._project_data_provider = data_provider

    def start_server(self) -> int:
        self._running = True
        self._collect_local_ips()
        self.http_port = self._start_http_server()
        self._start_udp_listener()
        logging.info(f"局域网传输服务已启动 - 设备: {self.device_name}, HTTP端口: {self.http_port}")
        return self.http_port

    def stop_server(self):
        self._running = False
        if self._http_server:
            try:
                self._http_server.shutdown()
            except Exception:
                pass
            self._http_server = None
        if self._udp_socket:
            try:
                self._udp_socket.close()
            except Exception:
                pass
            self._udp_socket = None
        logging.info("局域网传输服务已停止")

    def start_discovery(self):
        t = threading.Thread(target=self._discovery_loop, daemon=True)
        t.start()
        self._threads.append(t)

    def fetch_projects(self, target_ip: str, target_port: int) -> list:
        import urllib.request
        url = f"http://{target_ip}:{target_port}/projects"
        req = urllib.request.Request(url, headers={"X-Device-Name": self.device_name})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("projects", [])

    def fetch_project_data(self, target_ip: str, target_port: int, project_id: str) -> dict:
        import urllib.request
        url = f"http://{target_ip}:{target_port}/projects/{project_id}"
        req = urllib.request.Request(url, headers={"X-Device-Name": self.device_name})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def send_save_data(self, target_ip: str, target_port: int, save_data: dict) -> bool:
        import urllib.request
        url = f"http://{target_ip}:{target_port}/upload"
        body = json.dumps(save_data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Device-Name": self.device_name,
                "X-Platform": "desktop",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("status") == "ok"
        except Exception as e:
            logging.error(f"发送存档失败: {e}")
            raise

    def probe_device(self, ip: str) -> Optional[DeviceInfo]:
        import urllib.request
        for port in range(HTTP_PORT_START, HTTP_PORT_END):
            try:
                url = f"http://{ip}:{port}/info"
                req = urllib.request.Request(url, headers={"X-Device-Name": self.device_name})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    info = json.loads(resp.read().decode("utf-8"))
                    device = DeviceInfo(
                        name=info.get("name", ip),
                        http_port=info.get("http_port", port),
                        platform=info.get("platform", "unknown"),
                        ip=ip,
                    )
                    if not self._is_local_ip(ip) and self._on_device_found:
                        self._on_device_found(device)
                    return device
            except Exception:
                continue
        return None

    def _start_http_server(self) -> int:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                logging.debug(f"HTTP: {format % args}")

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/info":
                    self._handle_info()
                elif path == "/projects":
                    self._handle_project_list()
                elif path.startswith("/projects/"):
                    project_id = unquote(path[len("/projects/"):])
                    self._handle_project_download(project_id)
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path == "/upload":
                    self._handle_upload()
                else:
                    self.send_error(404)

            def _handle_info(self):
                info = {
                    "name": service.device_name,
                    "platform": "desktop",
                    "http_port": service.http_port,
                }
                self._send_json(info)

            def _handle_project_list(self):
                if not service._project_list_provider:
                    self._send_json({"projects": []})
                    return
                try:
                    projects = service._project_list_provider()
                    self._send_json({"projects": projects})
                except Exception as e:
                    logging.error(f"获取项目列表失败: {e}")
                    self._send_json({"error": str(e)}, 500)

            def _handle_project_download(self, project_id: str):
                if not service._project_data_provider:
                    self._send_json({"error": "未配置项目数据提供者"}, 404)
                    return
                try:
                    save_data = service._project_data_provider(project_id)
                    if save_data is None:
                        self._send_json({"error": f"项目 {project_id} 不存在"}, 404)
                        return
                    self._send_json(save_data)
                except Exception as e:
                    logging.error(f"获取项目数据失败: {e}")
                    self._send_json({"error": str(e)}, 500)

            def _handle_upload(self):
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length == 0:
                        self._send_json({"error": "空请求体"}, 400)
                        return
                    body = self.rfile.read(content_length)
                    save_data = json.loads(body.decode("utf-8"))
                    sender_name = self.headers.get("X-Device-Name", "未知设备")
                    if service._on_file_received:
                        service._on_file_received(save_data, sender_name)
                    self._send_json({"status": "ok", "message": "存档已接收"})
                except json.JSONDecodeError:
                    self._send_json({"error": "无效的JSON格式"}, 400)
                except Exception as e:
                    logging.error(f"处理上传失败: {e}")
                    self._send_json({"error": str(e)}, 500)

            def _send_json(self, data: dict, code: int = 200):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        for port in range(HTTP_PORT_START, HTTP_PORT_END):
            try:
                from socketserver import ThreadingMixIn

                class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
                    daemon_threads = True

                server = ThreadedHTTPServer(("0.0.0.0", port), Handler)
                self._http_server = server
                t = threading.Thread(target=server.serve_forever, daemon=True)
                t.start()
                self._threads.append(t)
                return port
            except OSError:
                continue

        raise RuntimeError("无法启动HTTP服务器：所有端口都被占用")

    def _start_udp_listener(self):
        t = threading.Thread(target=self._udp_listen_loop, daemon=True)
        t.start()
        self._threads.append(t)

    def _udp_listen_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", UDP_PORT))
            sock.settimeout(1.0)
            self._udp_socket = sock

            while self._running:
                try:
                    data, addr = sock.recvfrom(4096)
                    message = data.decode("utf-8").strip()
                    self._handle_udp_message(message, addr, sock)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logging.debug(f"UDP接收错误: {e}")
        except Exception as e:
            logging.error(f"UDP监听启动失败: {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _handle_udp_message(self, message: str, addr: Tuple[str, int], sock: socket.socket):
        parts = message.split("|")
        if len(parts) < 2 or parts[0] != PROTOCOL_MAGIC:
            return
        action = parts[1]
        if action == "DISCOVER" and len(parts) >= 5:
            response = f"{PROTOCOL_MAGIC}|FOUND|{self.device_name}|{self.http_port}|desktop"
            sock.sendto(response.encode("utf-8"), addr)
            logging.debug(f"响应发现请求: {addr[0]}")
        elif action == "FOUND" and len(parts) >= 5:
            device = DeviceInfo(
                name=parts[2], http_port=int(parts[3]),
                platform=parts[4], ip=addr[0],
            )
            if not self._is_local_ip(addr[0]) and self._on_device_found:
                self._on_device_found(device)

    def _discovery_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2.0)
            message = f"{PROTOCOL_MAGIC}|DISCOVER|{self.device_name}|{self.http_port}|desktop"
            for i in range(BROADCAST_COUNT):
                if not self._running:
                    break
                try:
                    sock.sendto(message.encode("utf-8"), ("<broadcast>", UDP_PORT))
                    while True:
                        try:
                            data, addr = sock.recvfrom(4096)
                            resp = data.decode("utf-8").strip()
                            parts = resp.split("|")
                            if len(parts) >= 5 and parts[0] == PROTOCOL_MAGIC and parts[1] == "FOUND":
                                device = DeviceInfo(
                                    name=parts[2], http_port=int(parts[3]),
                                    platform=parts[4], ip=addr[0],
                                )
                                if not self._is_local_ip(addr[0]) and self._on_device_found:
                                    self._on_device_found(device)
                        except socket.timeout:
                            break
                except Exception as e:
                    logging.debug(f"广播发送失败: {e}")
                time.sleep(BROADCAST_INTERVAL)
            sock.close()
        except Exception as e:
            logging.error(f"发现循环错误: {e}")
