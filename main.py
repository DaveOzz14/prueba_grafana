# IMPORTANT: otel_setup MUST be the very first import.
# It registers TracerProvider, MeterProvider, and LoggerProvider globally
# before any other module initialises logging or the FastAPI app.
import otel_setup  # noqa: F401

import logging
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import StatusCode

from otel_setup import meter, tracer

# ---------------------------------------------------------------------------
# Logger
# The OTel logging bridge (LoggingHandler + LoggingInstrumentor) is already
# attached to the root logger inside otel_setup.  No basicConfig needed here.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="prueba_grafana", version="1.0.0")

# Auto-instrument HTTP server spans (must be called immediately after app creation)
FastAPIInstrumentor.instrument_app(app)

templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Business Metrics — RED pattern for the login flow
# Instruments are created ONCE at module load and reused on every request.
# ---------------------------------------------------------------------------

login_requests_total = meter.create_counter(
    name="login.requests.total",
    description="Total login HTTP requests received (page load + form submission)",
    unit="1",
)

login_page_views_total = meter.create_counter(
    name="login.page.views.total",
    description="Total times the login HTML page was served (GET /)",
    unit="1",
)

login_errors_total = meter.create_counter(
    name="login.errors.total",
    description="Total login errors that resulted in a 5xx HTTP response",
    unit="1",
)

login_duration_seconds = meter.create_histogram(
    name="login.request.duration.seconds",
    description="Wall-clock duration of the login form submission handler (seconds)",
    unit="s",
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    GET /
    Serves the login HTML page.
    Authorised instrumentation scope: Login flow — step 1 of 2.
    """
    with tracer.start_as_current_span(
        "login.page.get",
        kind=trace.SpanKind.SERVER,
    ) as span:
        # ── Span attributes ────────────────────────────────────────────────
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.route", "/")
        span.set_attribute("http.url", str(request.url))
        span.set_attribute(
            "http.user_agent", request.headers.get("user-agent", "unknown")
        )
        span.set_attribute("login.action", "page_load")

        # ── Metrics ────────────────────────────────────────────────────────
        _labels = {"http.method": "GET", "http.route": "/"}
        login_requests_total.add(1, _labels)
        login_page_views_total.add(1, {"http.route": "/"})

        # ── Logs ───────────────────────────────────────────────────────────
        logger.info(
            "Login page requested — client=%s",
            request.client.host if request.client else "unknown",
        )

        span.set_attribute("http.status_code", 200)
        return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """
    POST /login
    Processes the login form submission.
    Authorised instrumentation scope: Login flow — step 2 of 2.

    NOTE: Contains an intentional ZeroDivisionError to demonstrate full
    exception capture: span.record_exception(), ERROR status,
    error metric increment, and structured error log — all correlated
    via the same trace_id.
    """
    with tracer.start_as_current_span(
        "login.form.submit",
        kind=trace.SpanKind.SERVER,
    ) as span:
        _start = time.perf_counter()

        # ── Span attributes ────────────────────────────────────────────────
        span.set_attribute("http.method", "POST")
        span.set_attribute("http.route", "/login")
        span.set_attribute("user.name", username)
        span.set_attribute("login.action", "form_submit")
        span.set_attribute(
            "http.user_agent", request.headers.get("user-agent", "unknown")
        )

        # ── Metrics (request counter) ──────────────────────────────────────
        login_requests_total.add(
            1, {"http.method": "POST", "http.route": "/login"}
        )

        # ── Log: attempt received ──────────────────────────────────────────
        logger.info(
            "Login attempt received — user=%s",
            username,
        )

        try:
            # 🔥 INTENTIONAL ERROR — ZeroDivisionError (original business logic)
            result = 10 / 0
            return {"message": "Nunca llegara aqui", "result": result}

        except Exception as exc:
            _duration = time.perf_counter() - _start

            # ── Record exception on the active span ────────────────────────
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, description=str(exc))
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)

            # ── Error metrics ──────────────────────────────────────────────
            login_errors_total.add(
                1,
                {
                    "http.method": "POST",
                    "http.route": "/login",
                    "error.type": type(exc).__name__,
                },
            )
            login_duration_seconds.record(
                _duration,
                {
                    "http.method": "POST",
                    "http.route": "/login",
                    "http.status_code": "500",
                },
            )

            # ── Error log (trace_id / span_id injected automatically) ──────
            logger.error(
                "Critical error during login — user=%s error_type=%s message=%s",
                username,
                type(exc).__name__,
                str(exc),
                exc_info=True,
            )

            raise exc
