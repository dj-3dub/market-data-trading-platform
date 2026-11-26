"""Optional OTel traces for the journal-backed Kafka market-data producer.

Never changes the tick payload or acknowledgement/sequence semantics.
"""
import os

from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode, SpanKind

_enabled = False
_initialized = False


def configure_tracing():
    global _initialized, _enabled
    if _initialized:
        return
    _initialized = True
    _enabled = os.getenv('OTEL_TRACES_ENABLED', 'false').lower() in ('1', 'true', 'yes')
    if not _enabled:
        return
    provider = TracerProvider(resource=Resource.create({
        'service.name': os.getenv('OTEL_SERVICE_NAME', 'market-data'),
        'deployment.environment.name': 'homelab',
    }))
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=os.getenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', 'http://alloy:4318/v1/traces'),
            timeout=3,
        ),
        max_queue_size=256,
        max_export_batch_size=64,
        schedule_delay_millis=2000,
    ))
    trace.set_tracer_provider(provider)


def publish_tick_with_trace(producer, topic, tick):
    """Preserve blocking Kafka acknowledgement and existing error propagation."""
    if not _enabled:
        return producer.send(topic, key=tick['symbol'], value=tick).get(timeout=5)

    tracer = trace.get_tracer('mdp.market-data.kafka-producer')
    with tracer.start_as_current_span(
        'kafka publish tick', kind=SpanKind.PRODUCER,
        attributes={
            'messaging.system': 'kafka',
            'messaging.destination.name': topic,
            'messaging.operation.name': 'send',
            # Keep symbol only; avoid trace-per-sequence attributes/cardinality.
            'market.symbol': tick['symbol'],
        },
    ) as span:
        carrier = {}
        propagate.inject(carrier)
        headers = [(key, value.encode('utf-8')) for key, value in carrier.items()]
        try:
            result = producer.send(topic, key=tick['symbol'], value=tick, headers=headers).get(timeout=5)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        return result
