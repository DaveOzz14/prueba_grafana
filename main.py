# ==========================================================
# GRAFANA CLOUD + FASTAPI + OPENTELEMETRY (ALL-IN-ONE)
# ==========================================================
import os
import logging
import atexit
import time

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ---------- OTEL ----------
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

# ==========================================================
# VARIABLES (GRAFANA CLOUD)
# ==========================================================
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"

OTLP_ENDPOINT = "https://otlp-gateway-prod-us-east-2.grafana.net/otlp"

HEADERS = {
    "Authorization": "Basic MTUzOTU3NTpnbGNfZXlKdklqb2lNVFk0TVRRM09DSXNJbTRpT2lKemRHRmpheTB4TlRNNU5UYzFMVzkwYkhBdGQzSnBkR1V0WjNKaFptRnVNVEF3TURBd01EQXdNQ0lzSW1zaU9pSTBiVFl6TUdKd05UYzJSR0pvVkRNMlowVnBWRkprT1dFaUxDSnRJanA3SW5JaU9pSndjbTlrTFhWekxXVmhjM1F0TUNKOWZRPT0="  # 👈 pega aquí tu base64
}

SERVICE_NAME = "prueba_observability"

# ==========================================================
# LOGGING
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("app")

# ==========================================================
# RESOURCE
# ==========================================================
resource = Resource.create({
    "service.name": SERVICE_NAME,
    "deployment.environment": "production",
})

# ==========================================================
# TRACING
# ==========================================================
trace_provider = TracerProvider(resource=resource)

trace_provider.add_span_processor(
    SimpleSpanProcessor(
        OTLPSpanExporter(
            endpoint=f"{OTLP_ENDPOINT}/v1/traces",
            headers=HEADERS,
        )
    )
)

trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# ==========================================================
# METRICS
# ==========================================================
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(
        endpoint=f"{OTLP_ENDPOINT}/v1/metrics",
        headers=HEADERS,
    ),
    export_interval_millis=5000,
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader],
)

metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

login_counter = meter.create_counter(
    "login_attempts_total",
    description="Cantidad de intentos de login"
)

error_counter = meter.create_counter(
    "login_errors_total",
    description="Errores en login"
)

# ==========================================================
# FASTAPI
# ==========================================================
app = FastAPI()

# Middleware OTEL (CRÍTICO)

FastAPIInstrumentor().instrument_app(app)
app.add_middleware(OpenTelemetryMiddleware)
templates = Jinja2Templates(directory="templates")

# ==========================================================
# BUSINESS ENDPOINTS
# ==========================================================

# -----------------------------
# Login Page
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):

    with tracer.start_as_current_span("business.login_page") as span:
        span.set_attribute("business.step", "load_login")
        logger.info("Usuario abrió página de login")

    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


# -----------------------------
# Login (ERROR FLOW)
# -----------------------------
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):

    with tracer.start_as_current_span("business.login_attempt") as span:
        span.set_attribute("user.name", username)

        login_counter.add(1)
        logger.info(f"Intento login {username}")

        try:
            10 / 0

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("error", True)
            error_counter.add(1)
            logger.error("Error login", exc_info=True)
            raise


# ==========================================================
# SHUTDOWN CLEAN (IMPORTANTE)
# ==========================================================
@atexit.register
def shutdown():
    trace.get_tracer_provider().shutdown()
