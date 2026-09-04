"""DeepSeek API 客户端封装

使用 openai 兼容接口调用 DeepSeek API，提供文本和 JSON 两种调用模式。

注意：openai 包在 Streamlit 脚本运行器中模块级导入会导致静默崩溃（页面空白）。
因此将 from openai import OpenAI 移至 _get_client() 函数内（惰性导入），
并用 from __future__ import annotations 使类型标注在运行时不被求值。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_API_TIMEOUT

logger = logging.getLogger(__name__)

_client = None  # type: OpenAI | None (lazy import; see _get_client)
_last_api_key: str | None = None
_last_base_url: str | None = None
_lock = threading.Lock()


def reset_client() -> None:
    """强制清空客户端缓存，下次调用 _get_client() 将使用当前环境变量重建。

    应在侧边栏 API Key 或 Base URL 变更后立即调用，确保旧连接不被复用。
    """
    global _client, _last_api_key, _last_base_url
    with _lock:
        _client = None
        _last_api_key = None
        _last_base_url = None
        logger.info("OpenAI client forcefully reset — will rebuild on next call")


def _get_client() -> OpenAI:
    """获取 OpenAI 客户端实例，支持运行时 API Key / Base URL 更新。

    Streamlit 长连接场景下，用户在侧边栏修改 API Key 或 Base URL 后，
    下一次调用会自动使用新配置重建客户端。

    注意：导入 openai 包在 Streamlit 脚本运行器中会崩溃，
    因此将 from openai import OpenAI 放在函数内进行惰性导入。
    """
    from openai import OpenAI  # noqa: F811 — lazy import 避免 Streamlit 崩溃

    global _client, _last_api_key, _last_base_url
    # 优先读环境变量（Streamlit 侧边栏会写入 os.environ），
    # 值可能为空字符串（用户清空了输入框），此时回退到 .env 中的值
    env_key = os.getenv("DEEPSEEK_API_KEY")
    current_key = env_key if env_key else DEEPSEEK_API_KEY
    env_base = os.getenv("DEEPSEEK_BASE_URL")
    current_base = env_base if env_base else DEEPSEEK_BASE_URL

    if _client is None or _last_api_key != current_key or _last_base_url != current_base:
        with _lock:
            if _client is None or _last_api_key != current_key or _last_base_url != current_base:
                _client = OpenAI(
                    api_key=current_key,
                    base_url=current_base,
                    timeout=LLM_API_TIMEOUT,
                    max_retries=1,
                )
                _last_api_key = current_key
                _last_base_url = current_base
                # 日志仅显示 key 末4位，避免泄露
                logger.info(
                    "OpenAI client (re)initialized — key ending ...%s, base=%s",
                    current_key[-4:] if len(current_key) > 4 else "****",
                    current_base,
                )
    return _client


def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.0,
    response_format: dict | None = None,
    max_tokens: int = 4096,
    timeout: float | None = None,
) -> dict:
    """调用 LLM 获取文本响应。

    返回值统一格式: {"content": str|None, "error": str|None, "usage": dict, "model": str}

    重要: 调用者必须检查 error 字段判断成功/失败，而非检查 content 的真假值。
    合法的 LLM 响应可能返回空字符串 content=""，此时 error 为 None 表示调用成功。

    model 默认值从 os.environ 动态读取（而非导入时冻结），以支持 Streamlit 侧边栏
    运行时切换模型。若未指定 model 且环境变量为空，回退到 config.DEEPSEEK_MODEL。

    timeout: 单次调用超时（秒），None=用客户端默认 LLM_API_TIMEOUT。用于 Agent②
      汇总 LLM 调用（输入含全员标签，需比单员工 30s 更长）。per-call 覆盖，不影响
      客户端单例与 Agent① 调用。
    """
    if model is None:
        model = (os.getenv("DEEPSEEK_MODEL") or "").strip() or DEEPSEEK_MODEL

    try:
        client = _get_client()
    except Exception as e:
        logger.error(f"Failed to create API client: {e}")
        return {"content": None, "error": f"Client init failed: {e}", "usage": {}, "model": ""}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format
    if timeout is not None:
        # OpenAI SDK 支持 .create(timeout=...) per-call 覆盖客户端默认 timeout
        kwargs["timeout"] = timeout

    try:
        resp = client.chat.completions.create(**kwargs)
        if not resp.choices:
            return {
                "content": None,
                "error": "API returned empty choices list",
                "usage": {},
                "model": resp.model if resp.model else "",
            }
        msg = resp.choices[0].message
        finish_reason = resp.choices[0].finish_reason or ""
        content = msg.content if msg.content is not None else ""
        if content == "" and finish_reason != "stop":
            logger.warning(
                "LLM returned empty content (finish_reason=%s), retrying once...",
                finish_reason,
            )
            try:
                resp2 = client.chat.completions.create(**kwargs)
                if resp2.choices:
                    msg2 = resp2.choices[0].message
                    finish_reason2 = resp2.choices[0].finish_reason or ""
                    content2 = msg2.content if msg2.content is not None else ""
                    if content2:
                        return {
                            "content": content2,
                            "error": None,
                            "usage": {
                                "prompt_tokens": resp2.usage.prompt_tokens if resp2.usage else 0,
                                "completion_tokens": resp2.usage.completion_tokens if resp2.usage else 0,
                            },
                            "model": resp2.model or "",
                        }
            except Exception as e2:
                logger.error("LLM retry also failed: %s", e2)
            return {
                "content": None,
                "error": f"API returned empty content after retry (finish_reason={finish_reason})",
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                },
                "model": resp.model or "",
            }
        return {
            "content": content,
            "error": None,
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            },
            "model": resp.model or "",
        }
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return {"content": None, "error": str(e), "usage": {}, "model": ""}


def call_llm_json(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.0,
    json_schema: dict | None = None,
    max_tokens: int = 4096,
    timeout: float | None = None,
) -> dict:
    json_prompt = prompt + "\n\n请严格按照上述 JSON 格式输出，不要添加任何额外的解释文字。"
    json_system = system_prompt + "\n你必须且只能输出有效的 JSON，不要包含 markdown 代码块标记。"

    result = call_llm(
        prompt=json_prompt,
        system_prompt=json_system,
        model=model,
        temperature=temperature,
        response_format=None,  # 不传 response_format：DeepSeek-V4-Pro 代理不支持
        max_tokens=max_tokens,
        timeout=timeout,
    )

    # ── 自动重试：空内容或 finish_reason 异常 → 降级为更短 prompt ──
    if result.get("error") is not None and "empty content" in result["error"]:
        logger.warning("LLM returned empty content, retrying with shorter prompt...")
        short_prompt = json_prompt[:2000]
        result = call_llm(
            prompt=short_prompt,
            system_prompt="你必须输出 JSON。",
            model=model,
            temperature=temperature,
            response_format=None,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    if result.get("error") is not None:
        return {
            "content": result.get("content"),
            "error": result.get("error"),
            "raw_content": None,
            "usage": result.get("usage", {}),
            "model": result.get("model", ""),
            "schema_validated": None if json_schema is None else False,
        }

    raw = result.get("content") or ""
    parsed = _try_parse_json(raw)
    if parsed is not None:
        pass  # 成功
    else:
        logger.error(f"JSON parse failed, raw content: {raw[:200]}...")
        return {
            "content": None,
            "error": f"JSON parse failed: Expecting value",
            "raw_content": raw[:500],
            "usage": result.get("usage", {}),
            "model": result.get("model", ""),
            "schema_validated": None if json_schema is None else False,
        }

    # 如果提供了 json_schema，校验解析后的数据
    schema_validated = None if json_schema is None else False
    if json_schema is not None:
        try:
            import jsonschema
        except ImportError:
            logger.error(
                "jsonschema not installed — schema validation unavailable. "
                "Install with: pip install jsonschema"
            )
            return {
                "content": None,
                "error": "jsonschema not installed — schema validation unavailable",
                "raw_content": result.get("content"),
                "usage": result.get("usage", {}),
                "model": result.get("model", ""),
                "schema_validated": False,
            }
        else:
            try:
                jsonschema.validate(parsed, json_schema)
                schema_validated = True
            except jsonschema.ValidationError as e:
                logger.error(f"JSON Schema validation failed: {e.message}")
                return {
                    "content": None,
                    "error": f"Schema validation failed: {e.message}",
                    "raw_content": json.dumps(parsed, ensure_ascii=False),
                    "usage": result.get("usage", {}),
                    "model": result.get("model", ""),
                    "schema_validated": False,
                }

    return {"content": parsed, "error": None, "raw_content": None, "usage": result.get("usage", {}), "model": result.get("model", ""), "schema_validated": schema_validated}


def _try_parse_json(raw: str) -> dict | list | None:
    """尝试从字符串中解析 JSON，支持多种格式。

    按优先级尝试：
    1. 直接 json.loads
    2. 从 ```json ... ``` 代码块提取
    3. 从 ``` ... ``` 代码块提取
    4. 从第一个 { 到最后一个 } 截取
    """
    # 1. 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. 提取 ```json ... ``` 代码块
    import re
    m = re.search(r"```(?:json)\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 提取 ``` ... ``` 代码块
    m = re.search(r"```\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 4. 从第一个 { 到最后一个 } 截取
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end+1])
        except json.JSONDecodeError:
            pass

    # 5. 修复截断的 JSON：尝试补全尾部（finish_reason=length 场景）
    if start != -1:
        try:
            repaired = _repair_truncated_json(raw, start)
            if repaired is not None:
                return repaired
        except Exception:
            pass

    return None


def _repair_truncated_json(raw: str, start: int = 0) -> dict | None:
    """修复截断的 JSON 对象：用正则提取完整 + 半截 key-value 对重建。

    finish_reason=length 时响应被截断，json.loads 因尾部不完整而失败。
    两轮提取：
      1. 完整字段（含闭合引号的字符串 / 数字 / 布尔 / null / 数组 / 对象）
      2. 截断字符串值：开引号在、闭引号缺失（finish_reason=length 最常见情形，
         字符串值被从中间切断）→ 取到下一个 ,"key" 或字符串末尾。
    """
    import re
    content = raw[start:]
    result: dict = {}

    # ── 第 1 轮：完整 key-value ──
    strict = (
        r'"([^"]+)"\s*:\s*'
        r'("[^"\\]*(?:\\.[^"\\]*)*"|\d+\.?\d*|true|false|null|\[[^\]]*\]|\{[^}]*\})'
    )
    for m in re.finditer(strict, content):
        key, val_str = m.group(1), m.group(2)
        if key in result:
            continue
        try:
            result[key] = json.loads(val_str)
        except (json.JSONDecodeError, ValueError):
            result[key] = val_str.strip('"')

    # ── 第 2 轮：截断字符串值（闭引号缺失）──
    # 值部分消费到：下一个 ,"key" 或 } 或 EOF。完整字符串不会被匹配
    # （其闭引号阻断消费，且其后是 " 而非 lookahead 要求的 ,/}/$）。
    trunc = r'"([^"]+)"\s*:\s*"((?:\\.|[^"\\])*)(?=\s*,\s*"|\s*\}|\s*$)'
    for m in re.finditer(trunc, content, re.DOTALL):
        key, partial = m.group(1), m.group(2)
        if key in result:
            continue
        # 尝试补全闭引号后解析（处理转义），失败则原样存为字符串
        try:
            result[key] = json.loads('"' + partial + '"')
        except (json.JSONDecodeError, ValueError):
            result[key] = partial

    if result and all(isinstance(k, str) for k in result):
        return result
    return None
