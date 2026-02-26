# OpenTelemetry Instrumentation Summary

## Repository
`DaveOzz14/prueba_grafana`

## Instrumented Branch
`app_otel`

---

## STEP 1 — Repository Analysis

| Property | Value |
|---|---|
| Language | Python 3.x |
| Framework | FastAPI |
| Server | Uvicorn (ASGI) |
| Templates | Jinja2 (server-side HTML) |
| Dependency manager | pip (`requirements.txt`) |
| Original dependencies | `fastapi`, `uvicorn`, `jinja2`, `python-multipart` |

---

## STEP 1.5 — Authorized Flow Scope

**Authorized flow: Login (`/`)**

| File | Role |
|---|---|
| `main.py` | FastAPI app, `GET /` and `POST /login` route handlers |
| `templates/login.html` | Login form HTML (server-rendered) |

**Excluded flows:** None exist in this repository (no `/hipotecario/solicitud` or any other unauthorized flow).

---

## STEP 2 — OTel SDK & Compatibility

| Package | Version | Purpose |
|---|---|---|
| `opentelemetry-api` | `1.27.0` | Core API (tracer, meter, logger interfaces) |
| `opentelemetry-sdk` | `1.27.0` | SDK implementation (providers, processors) |
| `opentelemetry-exporter-otlp-proto-http` | `1.27.0` | OTLP http/protobuf transport |
| `opentelemetry-instrumentation-fastapi` | `0.48b0` | FastAPI auto-instrumentation |
| `opentelemetry-instrumentation-logging` | `0.48b0` | Python logging → OTel bridge (trace_id injection) |

> All versions are mutually compatible. `0.48b0` contrib is the official release paired with SDK `1.27.0`.

---

## STEP 3 — Environment Configuration

All configuration is read **exclusively from OS environment variables**. No `.env` file is used or required.

### Required variables

```sh
export OTEL_SERVICE_NAME=prueba_observability
export OTEL_EXPORTER_OTLP_ENDPOINT=https://<grafana-otlp-gateway>/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64-instanceid:apikey>"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=dev"
```

### Optional per-signal overrides

```sh
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://.../otlp/v1/traces
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://.../otlp/v1/metrics
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://.../otlp/v1/logs
```

> **Transport:** `http/protobuf` only (OTLP over HTTP with Protobuf encoding).

---

## STEP 4 — Instrumentation Architecture

### Single bootstrap file: `otel_setup.py`

Must be imported as the **first** import in `main.py`:
```python
import otel_setup  # noqa: F401
```

| Component | Implementation |
|---|---|
| TracerProvider | `TracerProvider(resource)` + `BatchSpanProcessor` + `OTLPSpanExporter` |
| MeterProvider | `MeterProvider(resource, readers=[PeriodicExportingMetricReader(60s)])` + `OTLPMetricExporter` |
| LoggerProvider | `LoggerProvider(resource)` + `BatchLogRecordProcessor` + `OTLPLogExporter` |
| Logging bridge | `LoggingHandler` attached to root logger (exports stdlib logs via OTLP) |
| Trace correlation | `LoggingInstrumentor().instrument(set_logging_format=True)` — injects `trace_id`/`span_id` into every log record |
| HTTP auto-instrumentation | `FastAPIInstrumentor.instrument_app(app)` in `main.py` immediately after app creation |

Exported instances: `tracer`, `meter` (imported by `main.py`)

---

## STEP 5 — Manual Business Spans

| Span Name | Route | Kind | Key Attributes |
|---|---|---|---|
| `login.page.get` | `GET /` | SERVER | `http.method`, `http.route`, `http.url`, `http.user_agent`, `login.action=page_load` |
| `login.form.submit` | `POST /login` | SERVER | `http.method`, `http.route`, `user.name`, `login.action=form_submit`, `error.type`, `error.message`, `http.status_code` |

**Exception handling (both spans):**
- `span.record_exception(exc)` — attaches exception event with stack trace
- `span.set_status(StatusCode.ERROR, description)` — marks span as ERROR

---

## STEP 6 — Metrics & Logs

### Metrics (RED pattern)

| Metric | Type | Labels | Description |
|---|---|---|---|
| `login.requests.total` | Counter | `http.method`, `http.route` | All login requests |
| `login.page.views.total` | Counter | `http.route` | Login page loads (GET /) |
| `login.errors.total` | Counter | `http.method`, `http.route`, `error.type` | 5xx errors |
| `login.request.duration.seconds` | Histogram | `http.method`, `http.route`, `http.status_code` | Form submission duration |

### Logs

- Exported via `OTLPLogExporter` → `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`
- Every log record includes `otelTraceID`, `otelSpanID`, `otelServiceName` (injected by `LoggingInstrumentor`)
- Trace ↔ Log correlation is automatic for all `logger.*` calls inside active spans

---

## STEP 7 — Files Changed

| File | Status | Description |
|---|---|---|
| `otel_setup.py` | **NEW** | Single OTel bootstrap (providers, exporters, log bridge) |
| `main.py` | **MODIFIED** | Manual spans, business metrics, structured logs, `FastAPIInstrumentor` |
| `requirements.txt` | **MODIFIED** | Added 5 OTel dependencies |
| `summary_instrumentation.md` | **NEW** | This document |
| `templates/login.html` | Unchanged | Login HTML template |
| `.gitignore` | Unchanged | Python gitignore |

---

## STEP 8.5 — New OTel Dependencies (Installation Command)

The following packages were **not** previously in the project and were added exclusively for OpenTelemetry instrumentation:

| Package | Version | Purpose |
|---|---|---|
| `opentelemetry-api` | `1.27.0` | Traces, Metrics, Logs API interfaces |
| `opentelemetry-sdk` | `1.27.0` | TracerProvider, MeterProvider, LoggerProvider, Batch processors |
| `opentelemetry-exporter-otlp-proto-http` | `1.27.0` | OTLP http/protobuf exporter for all three signals |
| `opentelemetry-instrumentation-fastapi` | `0.48b0` | Auto-instrumentation for FastAPI HTTP server spans |
| `opentelemetry-instrumentation-logging` | `0.48b0` | Python logging bridge — injects trace_id/span_id into log records |

### Copy-paste installation command

```sh
pip install \
  opentelemetry-api==1.27.0 \
  opentelemetry-sdk==1.27.0 \
  opentelemetry-exporter-otlp-proto-http==1.27.0 \
  "opentelemetry-instrumentation-fastapi==0.48b0" \
  "opentelemetry-instrumentation-logging==0.48b0"
```

---

## Grafana Cloud Configuration Reference

Obtain your OTLP endpoint and credentials from:
`Grafana Cloud Portal → Stack → OpenTelemetry`

```sh
export OTEL_SERVICE_NAME=prueba_observability
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(instanceId:apiKey)>"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=dev"
```

### Start the application

```sh
uvicorn main:app --host 0.0.0.0 --port 8000
```

Traces, metrics, and logs will begin shipping to Grafana Cloud on first request.
