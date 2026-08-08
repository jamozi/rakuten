from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = Path("python/raos/adapters/openai_responses.py")
TEST_PATH = Path("tests/st0703/test_adapter.py")


def replace_definitions(
    path: Path,
    *,
    methods: dict[tuple[str, str], str],
    functions: dict[str, str],
) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text, filename=str(path))
    replacements: list[tuple[int, int, str]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                key = (node.name, child.name)
                replacement = methods.get(key)
                if replacement is not None:
                    if child.end_lineno is None:
                        raise SystemExit(f"missing end line for {key}")
                    replacements.append(
                        (child.lineno - 1, child.end_lineno, replacement.rstrip("\n") + "\n")
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            replacement = functions.get(node.name)
            if replacement is not None:
                if node.end_lineno is None:
                    raise SystemExit(f"missing end line for {node.name}")
                replacements.append(
                    (node.lineno - 1, node.end_lineno, replacement.rstrip("\n") + "\n")
                )

    expected = len(methods) + len(functions)
    if len(replacements) != expected:
        raise SystemExit(
            f"expected {expected} definitions in {path}, found {len(replacements)}"
        )

    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    path.write_text("".join(lines), encoding="utf-8", newline="")


replace_definitions(
    SOURCE_PATH,
    methods={
        (
            "OpenAIResponsesAdapter",
            "execute",
        ): '''    def execute(self, request: StructuredTaskRequest) -> ProviderResult:
        if type(request) is not StructuredTaskRequest:
            raise TypeError("request must be an exact StructuredTaskRequest")
        if request.model_route_version != self._route.route_version:
            raise ProviderError(ProviderErrorCode.ROUTE_MISMATCH)
        payload = self._request_payload(request)
        started_ns = self._safe_monotonic_ns()
        response: object = None
        provider_failure: ProviderErrorCode | None = None
        try:
            configured_client = self._client.with_options(
                max_retries=0,
                timeout=self._route.timeout_seconds,
            )
            response = configured_client.responses.create(**payload)
        except Exception as exc:
            if type(exc) is ProviderError:
                provider_failure = exc.code
            else:
                provider_failure = _classify_provider_error(exc)
        if provider_failure is not None:
            raise ProviderError(provider_failure)
        received_at = self._safe_clock()
        finished_ns = self._safe_monotonic_ns()
        response_document = _response_mapping(response)
        return self._classify_response(
            request=request,
            response=response_document,
            received_at=received_at,
            latency_ms=_latency_ms(started_ns, finished_ns),
            provider_request_id=_provider_request_id(response),
        )
''',
        (
            "OpenAIResponsesAdapter",
            "_request_payload",
        ): '''    def _request_payload(self, request: StructuredTaskRequest) -> dict[str, object]:
        schema_document: object = None
        schema_invalid = False
        try:
            schema_document = json.loads(
                request.output_schema.document_bytes.decode("utf-8", errors="strict")
            )
            Draft202012Validator.check_schema(schema_document)
        except Exception:
            schema_invalid = True
        if schema_invalid:
            raise ProviderError(ProviderErrorCode.INVALID_SCHEMA)
        return {
            "model": self._route.model_id,
            "input": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.output_schema.name,
                    "strict": True,
                    "schema": schema_document,
                }
            },
            "store": False,
            "tools": [],
            "max_output_tokens": request.max_output_tokens,
            "reasoning": {"effort": self._route.reasoning_effort.value},
        }
''',
        (
            "OpenAIResponsesAdapter",
            "_record",
        ): '''    def _record(self, exchange: ProviderExchange) -> ArtifactRef:
        artifact: object = None
        recorder_failed = False
        try:
            artifact = self._recorder.record(exchange)
        except Exception:
            recorder_failed = True
        if recorder_failed or type(artifact) is not ArtifactRef:
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
        artifact_ref = cast(ArtifactRef, artifact)
        if (
            artifact_ref.sha256 != exchange.sha256
            or artifact_ref.byte_size != len(exchange.canonical_bytes)
            or artifact_ref.content_type != "application/json"
        ):
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
        return artifact_ref
''',
        (
            "OpenAIResponsesAdapter",
            "_calculate_pricing",
        ): '''    def _calculate_pricing(self, usage: ProviderUsage) -> PricingResult:
        pricing: object = None
        calculator_failed = False
        try:
            pricing = self._cost_calculator.calculate(
                usage,
                self._route.pricing_quote,
            )
        except Exception:
            calculator_failed = True
        if calculator_failed:
            raise ProviderError(ProviderErrorCode.PRICING_MISSING)
        if type(pricing) is not PricingResult:
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        pricing_result = cast(PricingResult, pricing)
        if (
            pricing_result.quote_id != self._route.pricing_quote.quote_id
            or pricing_result.quote_sha256 != self._route.pricing_quote.quote_sha256
            or pricing_result.native_currency
            != self._route.pricing_quote.native_currency
        ):
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        return pricing_result
''',
        (
            "OpenAIResponsesAdapter",
            "_safe_clock",
        ): '''    def _safe_clock(self) -> datetime:
        normalized: datetime | None = None
        try:
            value = self._clock()
            if (
                type(value) is datetime
                and value.tzinfo is not None
                and value.utcoffset() == timezone.utc.utcoffset(None)
            ):
                normalized = value.replace(tzinfo=timezone.utc)
        except Exception:
            normalized = None
        if normalized is None:
            raise ProviderError(ProviderErrorCode.UNKNOWN)
        return normalized
''',
        (
            "OpenAIResponsesAdapter",
            "_safe_monotonic_ns",
        ): '''    def _safe_monotonic_ns(self) -> int:
        value: object = None
        clock_failed = False
        try:
            value = self._monotonic_ns()
        except Exception:
            clock_failed = True
        if clock_failed or type(value) is not int or value < 0:
            raise ProviderError(ProviderErrorCode.UNKNOWN)
        return cast(int, value)
''',
    },
    functions={
        "_response_mapping": '''def _response_mapping(response: object) -> Mapping[str, object]:
    value: object = None
    conversion_failed = False
    try:
        if isinstance(response, Mapping):
            value = response
        else:
            model_dump = getattr(response, "model_dump", None)
            to_dict = getattr(response, "to_dict", None)
            if callable(model_dump):
                value = model_dump(mode="json")
            elif callable(to_dict):
                value = to_dict()
            else:
                conversion_failed = True
    except Exception:
        conversion_failed = True
    if conversion_failed:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)

    bounded: Mapping[str, object] | None = None
    try:
        bounded = _bounded_mapping(value)
    except Exception:
        bounded = None
    if bounded is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return bounded
''',
        "_bounded_mapping": '''def _bounded_mapping(value: object) -> Mapping[str, object]:
    visits = 0
    active: set[int] = set()

    def snapshot(item: object, depth: int) -> object:
        nonlocal visits
        visits += 1
        if visits > _MAX_RESPONSE_GRAPH_VISITS or depth > _MAX_RESPONSE_GRAPH_DEPTH:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        if item is None or type(item) in {bool, int, str}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
            return item
        if not isinstance(item, (Mapping, list, tuple)):
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        identity = id(item)
        if identity in active:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        active.add(identity)
        try:
            if isinstance(item, Mapping):
                result: dict[str, object] = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
                    result[key] = snapshot(child, depth + 1)
                return result
            return [snapshot(child, depth + 1) for child in item]
        finally:
            active.remove(identity)

    frozen = snapshot(value, 0)
    if type(frozen) is not dict:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(dict[str, object], frozen)
''',
        "_usage": '''def _usage(value: object) -> ProviderUsage:
    document = _required_mapping(value)
    input_tokens = _exact_nonnegative_integer(document.get("input_tokens"))
    output_tokens = _exact_nonnegative_integer(document.get("output_tokens"))
    total_tokens = _exact_nonnegative_integer(document.get("total_tokens"))
    details = _required_mapping(document.get("input_tokens_details"))
    cached_tokens = _exact_nonnegative_integer(details.get("cached_tokens"))
    if total_tokens != input_tokens + output_tokens:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    usage: ProviderUsage | None = None
    try:
        usage = ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
        )
    except Exception:
        usage = None
    if usage is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return usage
''',
        "_unix_timestamp": '''def _unix_timestamp(value: object) -> datetime:
    timestamp: int | float
    if type(value) is int:
        timestamp = value
    elif type(value) is float and math.isfinite(value):
        timestamp = value
    else:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    if not 0 <= timestamp <= _MAX_SIGNED_BIGINT:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    converted: datetime | None = None
    try:
        converted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except Exception:
        converted = None
    if converted is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return converted
''',
        "_incomplete_reason": '''def _incomplete_reason(value: object) -> IncompleteReason:
    details = _required_mapping(value)
    reason = details.get("reason")
    parsed: IncompleteReason | None = None
    try:
        parsed = IncompleteReason(reason)
    except Exception:
        parsed = None
    if parsed is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return parsed
''',
        "_structured_output": '''def _structured_output(
    content: str,
    request: StructuredTaskRequest,
) -> CanonicalJsonObject:
    output: CanonicalJsonObject | None = None
    try:
        output = CanonicalJsonObject.from_bytes(
            content.encode("utf-8", errors="strict")
        )
    except Exception:
        output = None
    if output is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)

    validation_failure: ProviderErrorCode | None = None
    try:
        schema = json.loads(request.output_schema.document_bytes)
        Draft202012Validator(schema).validate(json.loads(output.canonical_bytes()))
    except SchemaError:
        validation_failure = ProviderErrorCode.INVALID_SCHEMA
    except Exception:
        validation_failure = ProviderErrorCode.MALFORMED_RESPONSE
    if validation_failure is not None:
        raise ProviderError(validation_failure)
    return output
''',
        "_provider_request_id": '''def _provider_request_id(response: object) -> str | None:
    try:
        value = getattr(response, "_request_id", None)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return _required_identifier(value, field="provider_request_id")
    except ProviderError:
        return None
''',
    },
)


test_text = TEST_PATH.read_text(encoding="utf-8")
sentinel = "def test_provider_errors_do_not_retain_exception_context("
if sentinel not in test_text:
    addition = r'''


@pytest.mark.parametrize(
    "error",
    (
        _StatusError(429),
        TimeoutError("SYNTHETIC_TEST_ONLY timeout diagnostic"),
        RuntimeError("SYNTHETIC_TEST_ONLY unknown diagnostic"),
    ),
)
def test_provider_errors_do_not_retain_exception_context(error: Exception) -> None:
    adapter, _, recorder = _adapter(error)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_malformed_output_does_not_retain_parser_context() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = "{not-json"
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.MALFORMED_RESPONSE
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_invalid_schema_does_not_retain_validator_context() -> None:
    request = _request()
    schema_bytes = b'{"type":7}'
    invalid_request = StructuredTaskRequest(
        task_code=request.task_code,
        model_route_version=request.model_route_version,
        prompt_version=request.prompt_version,
        input_artifact=request.input_artifact,
        output_schema=StructuredOutputSchema(
            name="invalid_schema_for_context_test",
            uri="urn:raos:synthetic:invalid-schema-context:v1",
            sha256=Sha256Digest.of(schema_bytes),
            document_bytes=schema_bytes,
        ),
        messages=request.messages,
        max_cost_jpy=request.max_cost_jpy,
        max_output_tokens=request.max_output_tokens,
        metadata=request.metadata,
    )
    adapter, client, recorder = _adapter(
        cast(dict[str, object], _fixture("success-structured.json")["transport"])[
            "body"
        ]
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(invalid_request)

    assert captured.value.code is ProviderErrorCode.INVALID_SCHEMA
    assert captured.value.__context__ is None
    assert client.responses_resource.calls == []
    assert recorder.record_calls == 0


def test_recorder_failure_does_not_retain_exception_context() -> None:
    class BrokenRecorder:
        def record(self, exchange):
            del exchange
            raise RuntimeError("SYNTHETIC_TEST_ONLY raw recorder context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=BrokenRecorder(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__context__ is None


def test_pricing_failure_does_not_retain_exception_context() -> None:
    class BrokenCalculator:
        def calculate(self, usage, quote):
            del usage, quote
            raise RuntimeError("SYNTHETIC_TEST_ONLY raw pricing context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=BrokenCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.PRICING_MISSING
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_invalid_recorder_result_fails_closed() -> None:
    class InvalidRecorder:
        def record(self, exchange):
            del exchange
            return object()

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=InvalidRecorder(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__context__ is None


def test_invalid_pricing_result_fails_closed() -> None:
    class InvalidCalculator:
        def calculate(self, usage, quote):
            del usage, quote
            return object()

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=InvalidCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.PRICING_MISMATCH
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_response_conversion_accessor_failure_is_sanitized() -> None:
    class ExplosiveResponse:
        def __deepcopy__(self, memo):
            del memo
            return self

        @property
        def model_dump(self):
            raise RuntimeError("SYNTHETIC_TEST_ONLY response accessor context")

    adapter, _, recorder = _adapter(ExplosiveResponse())

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.MALFORMED_RESPONSE
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_request_id_accessor_failure_is_ignored() -> None:
    class SDKResponse:
        def __init__(self, body: dict[str, object]) -> None:
            self._body = body

        def __deepcopy__(self, memo):
            del memo
            return self

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return copy.deepcopy(self._body)

        @property
        def _request_id(self) -> str:
            raise RuntimeError("SYNTHETIC_TEST_ONLY request-id accessor context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    response = SDKResponse(copy.deepcopy(cast(dict[str, object], transport["body"])))
    adapter, _, recorder = _adapter(response)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert result.metadata.provider_request_id is None
    assert recorder.record_calls == 1
'''
    TEST_PATH.write_text(test_text.rstrip("\n") + addition + "\n", encoding="utf-8")
