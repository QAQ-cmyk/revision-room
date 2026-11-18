"""Local provider profiles and bounded, single-request vision API adapters."""
from __future__ import annotations

import base64
import copy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid
import zlib

PRESETS = [
    {"id": "grok", "name": "Grok", "protocol": "openai", "baseUrl": "https://api.x.ai/v1", "tokenParam": "max_tokens"},
    {"id": "gemini", "name": "Gemini", "protocol": "openai", "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai", "tokenParam": "max_tokens"},
    {"id": "claude", "name": "Claude", "protocol": "anthropic", "baseUrl": "https://api.anthropic.com/v1", "tokenParam": "max_tokens"},
    {"id": "qwen", "name": "通义千问", "protocol": "openai", "baseUrl": "", "tokenParam": "max_tokens", "hint": "从百炼控制台复制当前工作空间和地域的兼容接口地址，选择支持图片的模型。"},
    {"id": "openai", "name": "OpenAI API", "protocol": "openai", "baseUrl": "https://api.openai.com/v1", "tokenParam": "max_completion_tokens"},
    {"id": "custom", "name": "自定义接口", "protocol": "openai", "baseUrl": "", "tokenParam": "max_tokens"},
]
PUBLIC_FIELDS = ("id", "name", "preset", "protocol", "baseUrl", "model", "maxTokens", "tokenParam", "noKey")
STORE_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RevisionRoom" / "ai_profiles.json"


def protect(value, decrypt=False):
    """Windows DPAPI, bound to the current Windows user; never plaintext fallback."""
    if os.name != "nt":
        raise ValueError("此版本的密钥保存需要 Windows 用户加密服务")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("密钥加密或读取失败，请在当前 Windows 账户重新填写")
    try:
        output = ctypes.string_at(result.data, result.size)
        return output.decode("utf-8") if decrypt else base64.b64encode(output).decode("ascii")
    finally:
        kernel.LocalFree(result.data)


def normalize_url(value):
    if not isinstance(value, str) or len(value) > 500 or any(c.isspace() for c in value):
        raise ValueError("请填写有效的 API 基础地址")
    try:
        url = urlsplit(value.rstrip("/"))
        local = url.hostname in ("127.0.0.1", "localhost", "::1")
        if (url.scheme != "https" and not (url.scheme == "http" and local)) or not url.hostname or not url.port and url.netloc.endswith(":"):
            raise ValueError()
        if url.username or url.password or url.query or url.fragment or any(c in value for c in "{}\\"):
            raise ValueError()
        value.encode("ascii")
    except (ValueError, UnicodeError):
        raise ValueError("API 地址须为 HTTPS；本机服务可用 HTTP。不要在地址中填写密钥或查询参数。") from None
    if url.path.endswith(("/chat/completions", "/messages", "/responses")):
        raise ValueError("请填写基础地址（通常以 /v1 结尾），不要包含 /chat/completions、/messages 或 /responses")
    return value.rstrip("/"), local


class ProfileStore:
    def __init__(self, path=STORE_PATH):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = {"defaultId": "codex", "profiles": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def public(self):
        with self.lock:
            return {"defaultId": self.data["defaultId"], "presets": copy.deepcopy(PRESETS), "profiles": [
                {**{k: p.get(k) for k in PUBLIC_FIELDS}, "hasKey": bool(p.get("encryptedKey"))} for p in self.data["profiles"]]}

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def draft(self, body):
        """Resolve a form without saving it; connection tests use exactly this draft."""
        with self.lock:
            old = next((p for p in self.data["profiles"] if p["id"] == body.get("id")), None)
            if body.get("id") and old is None:
                raise ValueError("接口已不存在，请重新添加")
            p = {k: body.get(k) for k in PUBLIC_FIELDS}
            p["id"] = old["id"] if old else uuid.uuid4().hex[:12]
            for key, label, limit in [("name", "接口名称", 80), ("model", "模型名称", 150)]:
                if not isinstance(p[key], str) or not p[key].strip() or len(p[key]) > limit or any(ord(c) < 32 for c in p[key]):
                    raise ValueError("请填写有效的" + label)
                p[key] = p[key].strip()
            if p["protocol"] not in ("openai", "anthropic") or p["tokenParam"] not in ("max_tokens", "max_completion_tokens"):
                raise ValueError("请选择有效的接口格式")
            if p["preset"] not in {x["id"] for x in PRESETS}:
                p["preset"] = "custom"
            if type(p["maxTokens"]) is not int or not 1024 <= p["maxTokens"] <= 32768:
                raise ValueError("输出上限须在 1024～32768 之间")
            p["baseUrl"], local = normalize_url(p["baseUrl"])
            p["noKey"] = p["noKey"] is True
            key = body.get("apiKey", "")
            if not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError("密钥含无效字符，请重新粘贴")
            if p["noKey"]:
                if not local:
                    raise ValueError("仅本机接口可以选择无需密钥")
                key = ""
            elif not key:
                if old and (old["baseUrl"] != p["baseUrl"] or old["protocol"] != p["protocol"]):
                    raise ValueError("更换地址或接口格式时，请重新填写密钥")
                if old and old.get("encryptedKey"):
                    key = protect(old["encryptedKey"], decrypt=True)
                else:
                    raise ValueError("请填写 API 密钥；它与网页登录或订阅额度不同")
            return {**p, "apiKey": key}

    def save(self, body):
        with self.lock:
            before = copy.deepcopy(self.data)
            p = self.draft(body)
            key = p.pop("apiKey")
            p["encryptedKey"] = protect(key) if key else ""
            existing = next((i for i, x in enumerate(self.data["profiles"]) if x["id"] == p["id"]), None)
            if existing is None:
                if len(self.data["profiles"]) >= 12:
                    raise ValueError("最多保存 12 个接口，请先移除不用的配置")
                self.data["profiles"].append(p)
            else:
                self.data["profiles"][existing] = p
            self.data["defaultId"] = p["id"]
            try:
                self._write()
            except OSError:
                self.data = before
                raise ValueError("配置未能写入本机，请检查目录权限和磁盘空间") from None
            return {**self.public(), "savedId": p["id"]}

    def resolve(self, profile_id):
        with self.lock:
            if profile_id == "codex":
                return None
            p = next((x for x in self.data["profiles"] if x["id"] == profile_id), None)
            if not p:
                raise ValueError("找不到所选 AI 接口，请先保存配置")
            return {**{k: p.get(k) for k in PUBLIC_FIELDS}, "apiKey": protect(p["encryptedKey"], decrypt=True) if p.get("encryptedKey") else ""}

    def select(self, profile_id):
        with self.lock:
            self.resolve(profile_id)
            before = self.data["defaultId"]
            self.data["defaultId"] = profile_id
            try:
                self._write()
            except OSError:
                self.data["defaultId"] = before
                raise ValueError("所选接口未能保存，请检查目录权限和磁盘空间") from None

    def delete(self, profile_id):
        with self.lock:
            if not any(p["id"] == profile_id for p in self.data["profiles"]):
                raise ValueError("找不到这个接口")
            before = copy.deepcopy(self.data)
            self.data["profiles"] = [p for p in self.data["profiles"] if p["id"] != profile_id]
            if self.data["defaultId"] == profile_id:
                self.data["defaultId"] = "codex"
            try:
                self._write()
            except OSError:
                self.data = before
                raise ValueError("配置未能移除，请检查目录权限和磁盘空间") from None
            return self.public()


class RequestCancelled(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_json(text):
    if not isinstance(text, str):
        raise ValueError("模型没有返回可读取的文字")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        result = json.loads(cleaned)
    except ValueError:
        raise ValueError("模型没有返回完整的 JSON 评审，请换支持结构化输出的视觉模型，或提高输出上限。未自动重试。") from None
    if not isinstance(result, dict):
        raise ValueError("模型返回的评审格式不正确")
    return result


def request_vision(profile, prompt, images, stop=None, test=False):
    """images: [(evidence label, PNG bytes)]. No retry or credential-bearing redirects."""
    if stop and stop.is_set():
        raise RequestCancelled()
    if not 1 <= len(images) <= 10 or sum(len(raw) for _, raw in images) > 24 * 1024 * 1024:
        raise ValueError("看图请求须包含 1～10 张截图，总大小不能超过 24 MB")
    content = [{"type": "text", "text": prompt}]
    native = profile["protocol"] == "anthropic"
    for label, raw in images:
        content.append({"type": "text", "text": "截图 ID / 说明：" + label})
        encoded = base64.b64encode(raw).decode("ascii")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded}} if native else
                       {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}})
    tokens = 1024 if test else profile["maxTokens"]
    payload = {"model": profile["model"], "messages": [{"role": "user", "content": content}],
               "max_tokens" if native else profile["tokenParam"]: tokens}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if profile.get("apiKey"):
        headers["x-api-key" if native else "Authorization"] = profile["apiKey"] if native else "Bearer " + profile["apiKey"]
    if native:
        headers["anthropic-version"] = "2023-06-01"
    url = profile["baseUrl"] + ("/messages" if native else "/chat/completions")
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    result = {}
    done = threading.Event()

    def send():
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=180) as response:
                data = response.read(4 * 1024 * 1024 + 1)
                if len(data) > 4 * 1024 * 1024:
                    raise ValueError("接口返回内容过大")
                def scrub(value):
                    if isinstance(value, str):
                        return value.replace(profile["apiKey"], "[密钥已隐藏]") if profile.get("apiKey") else value
                    if isinstance(value, list):
                        return [scrub(x) for x in value]
                    if isinstance(value, dict):
                        return {scrub(k): scrub(v) for k, v in value.items()}
                    return value
                result["body"] = scrub(json.loads(data.decode("utf-8")))
        except urllib.error.HTTPError as e:
            messages = {400: "请求格式或模型不支持图片，请核对模型和接口格式", 401: "密钥无效或已失效", 403: "账户或地域没有此模型的访问权限", 404: "接口地址或模型名称不存在", 413: "截图超出此接口的大小限制", 429: "额度不足或请求频率受限"}
            result["error"] = f"接口返回 HTTP {e.code}：" + messages.get(e.code, "服务暂不可用，或发生了不允许的地址跳转") + "。未自动重试。"
            e.close()
        except Exception:
            # Remote bodies and network exceptions can echo credentials. Never log or expose them.
            result["error"] = "接口连接失败、等待超时或返回内容无效，请核对地址、网络与服务状态。未自动重试。"
        finally:
            done.set()

    threading.Thread(target=send, daemon=True).start()
    deadline = time.monotonic() + 185
    while not done.wait(.15):
        if stop and stop.is_set():
            raise RequestCancelled()
        if time.monotonic() > deadline:
            raise ValueError("接口等待超时；已提交的请求可能仍由服务商处理，未自动重试。")
    if stop and stop.is_set():
        raise RequestCancelled()
    if result.get("error"):
        raise ValueError(result["error"])
    body = result.get("body")
    try:
        if native:
            finish = body.get("stop_reason")
            text = "".join(x["text"] for x in body["content"] if x.get("type") == "text")
        else:
            choice = body["choices"][0]
            finish = choice.get("finish_reason")
            text = choice["message"]["content"]
        if finish in ("length", "max_tokens", "content_filter", "refusal"):
            raise ValueError("模型输出被截断或拒绝；请检查模型和输出上限。未自动重试。")
        output = parse_json(text)
        usage = {k: v for k, v in (body.get("usage") or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        return output, usage
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError("接口返回格式与所选格式不匹配，或模型未返回文字结果") from None


def test_vision(profile):
    width, height = 160, 100
    row = bytes([0]) + bytes((30, 95, 230)) * (width // 2) + bytes((245, 130, 25)) * (width // 2)
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")
    prompt = '只观察附件图像。左右两半各是什么主要颜色？只返回 JSON：{"left":"英文小写颜色名","right":"英文小写颜色名"}。不要调用工具。'
    result, usage = request_vision(profile, prompt, [("连接测试图", png)], test=True)
    if result.get("left") != "blue" or result.get("right") != "orange":
        raise ValueError("接口有响应，但未正确识别测试图的左右颜色；尚不能确认看图可用。请核对视觉模型。")
    return {"ok": True, "message": "已连接，模型正确识别了测试图。实际游戏评审还会检查建议格式与截图引用。", "usage": usage}
