"""Small client for a user-configured, tool-calling Chat Completions endpoint."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ModelError(ValueError):
    pass


class ModelClient:
    def __init__(self):
        self.api_key = os.environ.get("LOCATOR_API_KEY", "")
        self.base_url = os.environ.get("LOCATOR_BASE_URL", "").rstrip("/")
        self.model = os.environ.get("LOCATOR_MODEL", "")

    @property
    def available(self):
        return bool(self.api_key and self.base_url and self.model)

    def complete(self, messages, tools=None):
        if not self.available:
            raise ModelError("模型未配置。请设置 LOCATOR_API_KEY、LOCATOR_BASE_URL 和 LOCATOR_MODEL，或使用规则检索演示。")
        url = urllib.parse.urlsplit(self.base_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme != "https" and not (url.scheme == "http" and local):
            raise ModelError("模型地址必须使用 HTTPS；本机模型允许 HTTP。")
        if url.username or url.password or url.query or url.fragment:
            raise ModelError("模型地址不能包含账号、查询参数或片段。")
        body = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:
            body.update(tools=tools, tool_choice="auto")
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        # Do not forward credentials through an HTTP redirect.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        try:
            opener = urllib.request.build_opener(NoRedirect)
            with opener.open(request, timeout=45) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ModelError("模型响应过大。")
                payload = json.loads(raw)
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("invalid message")
            return message
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise ModelError(f"模型服务返回 HTTP {status}，请检查模型配置或额度。") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ModelError("连接模型服务失败或超时，请检查地址和网络。") from None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            if isinstance(exc, ModelError):
                raise
            raise ModelError("模型服务的响应不符合 Chat Completions 格式。") from None
