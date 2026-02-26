"""
OpenTelemetry bootstrap for prueba_grafana.

MUST be imported FIRST in main.py as a side-effect:
    import otel_setup  # noqa: F401

Initialises:
    TracerProvider  --> OTLP http/protobuf --> /v1/traces
    MeterProvider   --> OTLP http/protobuf --> /v1/metrics
    LoggerProvider  --> OTLP http/protobuf --> /v1/logs

All configuration is read EXCLUSIVELY from OS environment variables.
No .env file is used or required.

Required OS environment variables
----------------------------------
OTEL_SERVICE_NAME                    (default: prueba_observability)
OTEL_EXPORTER_OTLP_ENDPOINT         Base OTLP endpoint
                                     e.g. https://otlp-gateway.grafana.net/otlp
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT  Full traces URL  (overrides base)
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT Full metrics URL (overrides base)
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT    Full logs URL    (overrides base)
OTEL_EXPORTER_OTLP_HEADERS          e.g. Authorization=Basic <base64-token>
OTEL_RESOURCE_ATTRIBUTES            e.g. deployment.environment=dev
"""

import logging
import os


from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_kv(raw: str) -> dict:
    """Parse 'key=value,key2=value2' into {key: value, key2: value2}."""
    result: dict = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------

_resource_attrs: dict = {
    "service.name": os.environ.get("OTEL_SERVICE_NAME", "prueba_observability"),
    "service.version": "1.0.0",
    "deployment.environment": "dev",
}
# Merge any additional attributes from OTEL_RESOURCE_ATTRIBUTES
_resource_attrs.update(_parse_kv(os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")))

resource = Resource.create(_resource_attrs)


# ---------------------------------------------------------------------------
# Shared OTLP headers (Authorization, etc.)
# ---------------------------------------------------------------------------

_headers: dict = _parse_kv(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))


# ---------------------------------------------------------------------------
# Endpoints  (http/protobuf ONLY)
# ---------------------------------------------------------------------------

_base_endpoint: str = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
)
_traces_endpoint: str = os.environ.get(
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", f"{_base_endpoint}/v1/traces"
)
_metrics_endpoint: str = os.environ.get(
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", f"{_base_endpoint}/v1/metrics"
)
_logs_endpoint: str = os.environ.get(
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", f"{_base_endpoint}/v1/logs"
)


# ---------------------------------------------------------------------------
# Traces — BatchSpanProcessor + OTLPSpanExporter
# ---------------------------------------------------------------------------

_tracer_provider = TracerProvider(resource=resource)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=_traces_endpoint, headers=_headers)
    )
)
trace.set_tracer_provider(_tracer_provider)

#: Use this tracer instance in every business file (main.py)
tracer = trace.get_tracer("prueba_grafana", "1.0.0")


# ---------------------------------------------------------------------------
# Metrics — PeriodicExportingMetricReader + OTLPMetricExporter
# ---------------------------------------------------------------------------

_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_metrics_endpoint, headers=_headers),
            export_interval_millis=60_000,
        )
    ],
)
metrics.set_meter_provider(_meter_provider)

#: Use this meter instance in every business file (main.py)
meter = metrics.get_meter("prueba_grafana", "1.0.0")


# ---------------------------------------------------------------------------
# Logs — BatchLogRecordProcessor + OTLPLogExporter
# ---------------------------------------------------------------------------

_logger_provider = LoggerProvider(resource=resource)
_logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=_logs_endpoint, headers=_headers)
    )
)
set_logger_provider(_logger_provider)

# Bridge: Python stdlib logging ──► OTel LoggerProvider (OTLP export)
_otel_log_handler = LoggingHandler(
    level=logging.DEBUG,
    logger_provider=_logger_provider,
)

# Inject otelTraceID / otelSpanID / otelServiceName into every log record
LoggingInstrumentor().instrument(set_logging_format=True)

# Console handler with trace-correlated format (stdout visibility)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(
    logging.Formatter(
        fmt=(
            "%(asctime)s [%(levelname)s] "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] "
            "%(name)s - %(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
)

# Attach both handlers to the root logger
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_console_handler)
_root_logger.addHandler(_otel_log_handler)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = ["tracer", "meter"]
