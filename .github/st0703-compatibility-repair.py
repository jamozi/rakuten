from pathlib import Path


def replace_top_level_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = f"def {name}("
    starts: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.startswith(marker):
            starts.append(offset)
        offset += len(line)
    if len(starts) != 1:
        raise SystemExit(f"expected exactly one top-level {name} in {path}")
    start = starts[0]
    end = len(text)
    offset = 0
    for line in text.splitlines(keepends=True):
        if offset > start and line.startswith(("def ", "class ", "@")):
            end = offset
            break
        offset += len(line)
    rendered = replacement.rstrip("\n") + "\n\n"
    path.write_bytes((text[:start] + rendered + text[end:]).encode("utf-8"))


adapter_path = Path("python/raos/adapters/openai_responses.py")
replace_top_level_function(
    adapter_path,
    "_unix_timestamp",
    """def _unix_timestamp(value: object) -> datetime:
    timestamp: int | float
    if type(value) is int:
        timestamp = value
    elif type(value) is float and math.isfinite(value):
        timestamp = value
    else:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    if not 0 <= timestamp <= _MAX_SIGNED_BIGINT:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except OverflowError, OSError, ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None
""",
)
replace_top_level_function(
    adapter_path,
    "_completed_content",
    """def _completed_content(value: object) -> tuple[str, str]:
    output = _required_sequence(value)
    message: Mapping[str, object] | None = None
    for item in output:
        candidate = _required_mapping(item)
        kind = candidate.get("type")
        if kind == "reasoning":
            continue
        if kind != "message" or message is not None:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        message = candidate
    if (
        message is None
        or message.get("role") != "assistant"
        or message.get("status") != "completed"
    ):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    content_items = _required_sequence(message.get("content"))
    if len(content_items) != 1:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    content = _required_mapping(content_items[0])
    kind = content.get("type")
    if kind == "refusal":
        refusal = content.get("refusal")
        if type(refusal) is not str or not refusal:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        return "refusal", ""
    if kind == "output_text":
        text = content.get("text")
        if type(text) is not str or not text:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        return "output_text", text
    raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
""",
)
replace_top_level_function(
    adapter_path,
    "_classify_provider_error",
    """def _classify_provider_error(error: Exception) -> ProviderErrorCode:
    name = type(error).__name__
    try:
        candidate_status = getattr(error, "status_code", None)
    except Exception:
        return ProviderErrorCode.UNKNOWN
    status: int | None
    if type(candidate_status) is int:
        status = candidate_status
    else:
        status = None
    if status == 429 or name == "RateLimitError":
        return ProviderErrorCode.RATE_LIMIT
    if status == 408 or name in {"APITimeoutError", "TimeoutError"}:
        return ProviderErrorCode.TIMEOUT
    if status == 401 or name == "AuthenticationError":
        return ProviderErrorCode.AUTHENTICATION
    if status == 403 or name == "PermissionDeniedError":
        return ProviderErrorCode.PERMISSION
    if status in {400, 404, 409, 422} or name in {
        "BadRequestError",
        "ConflictError",
        "NotFoundError",
        "UnprocessableEntityError",
    }:
        return ProviderErrorCode.INVALID_REQUEST
    if status in {502, 503, 504} or name == "APIConnectionError":
        return ProviderErrorCode.UNAVAILABLE
    if (status is not None and status >= 500) or name == "InternalServerError":
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.UNKNOWN
""",
)

test_path = Path("tests/st0703/test_adapter.py")
text = test_path.read_text(encoding="utf-8")
sentinel = "def test_sdk_float_created_at_is_accepted() -> None:"
if sentinel in text:
    raise SystemExit("compatibility regression tests already exist")
addition = r'''


def test_sdk_float_created_at_is_accepted() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    created_at = cast(int, body["created_at"])
    body["created_at"] = float(created_at)
    adapter, _, _ = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert result.metadata.response_created_at == datetime.fromtimestamp(
        float(created_at), tz=timezone.utc
    )


def test_reasoning_items_are_ignored_without_recording_summary() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    output = cast(list[object], body["output"])
    output.insert(
        0,
        {
            "id": "rs_synthetic_reasoning_001",
            "type": "reasoning",
            "summary": [
                {
                    "type": "summary_text",
                    "text": "SYNTHETIC_TEST_ONLY reasoning summary canary",
                }
            ],
        },
    )
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    recorded = recorder.read(result.raw_artifact)
    assert b"reasoning summary canary" not in recorded


def test_non_assistant_completed_message_fails_closed() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    message["role"] = "user"
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.MALFORMED_RESPONSE
    assert recorder.record_calls == 0


def test_status_code_accessor_failure_is_sanitized() -> None:
    class ExplosiveStatusError(RuntimeError):
        @property
        def status_code(self) -> int:
            raise RuntimeError("SYNTHETIC_TEST_ONLY status getter diagnostic")

    adapter, _, recorder = _adapter(ExplosiveStatusError("synthetic"))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.UNKNOWN
    assert "SYNTHETIC_TEST_ONLY" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert recorder.record_calls == 0


def test_http_408_is_classified_as_timeout() -> None:
    adapter, _, recorder = _adapter(_StatusError(408))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.TIMEOUT
    assert captured.value.retryable is True
    assert recorder.record_calls == 0
'''
test_path.write_bytes((text.rstrip("\n") + addition + "\n").encode("utf-8"))
