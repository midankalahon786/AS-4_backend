"""
src/common/telemetry.py
────────────────────────
Centralized OpenTelemetry configuration.
Supports disabling OpenTelemetry via:
  - OTEL_SDK_DISABLED=true (standard OpenTelemetry environment variable)
  - OTEL_ENABLED=false / ENABLE_OTEL=false
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from dotenv import load_dotenv

load_dotenv()

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def is_otel_enabled() -> bool:
    """
    Returns True only if OpenTelemetry is explicitly enabled
    and NOT disabled via environment variables.
    """
    # 1. Standard OpenTelemetry disabling flag
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() in ("true", "1", "yes"):
        return False

    # 2. Custom toggle flags
    if os.getenv("OTEL_ENABLED", "").strip().lower() in ("false", "0", "no"):
        return False
    if os.getenv("ENABLE_OTEL", "").strip().lower() in ("false", "0", "no"):
        return False

    # 3. Explicitly enabled
    if os.getenv("OTEL_ENABLED", "").strip().lower() in ("true", "1", "yes") or \
       os.getenv("ENABLE_OTEL", "").strip().lower() in ("true", "1", "yes"):
        return True

    # By default, if OTEL_SDK_DISABLED is unset and no explicit enable flag or endpoint is given,
    # keep it disabled to prevent connection errors to localhost:4317.
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_telemetry(
    app: FastAPI,
    service_name: str,
    excluded_urls: str = "health,/docs,/openapi.json",
) -> None:
    """
    Conditionally initialize OpenTelemetry tracer provider, OTLP exporter,
    and FastAPI instrumentation. If disabled, does nothing.
    """
    if not is_otel_enabled():
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        else:
            otlp_exporter = OTLPSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        try:
            trace.set_tracer_provider(provider)
        except Exception:
            pass  # Avoid error if TracerProvider is already set in current process

        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls)
        logger.info("OpenTelemetry initialized for %s", service_name)
    except Exception as exc:
        logger.warning("OpenTelemetry setup failed for %s: %s", service_name, exc)
