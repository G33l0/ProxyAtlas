# Architecture

ProxyAtlas is layered so each subsystem - discovery, validation, intelligence,
classification, monitoring and UI - can evolve independently. Engine code is
Qt-free and async; the UI drives it through Qt worker threads.

## Layers

```
UI (PyQt6)  ──uses──▶  Workers (QThread + asyncio)  ──drive──▶  Services / Engines  ──persist──▶  Database
   ▲                                                                   │
   └────────────────────── Event bus (progress/state) ◀───────────────┘
```

### core/
Constants, enums (`Protocol`, `ValidationStatus`, `Classification`, ...), the JSON
settings store, filesystem paths, rotating logging with credential redaction, a
Qt-free pub/sub event bus, structured exceptions, and the pipeline transport
dataclasses (`Endpoint`, `ProxyCandidate`, `ValidationResult`,
`IntelligenceResult`, `ClassificationResult`, `QualityScore`).

### database/
SQLAlchemy 2.0 typed models (16 tables), a WAL-tuned SQLite engine, a repository
module (all access is parameterized and identity-deduplicated), a serializable
`FilterSpec`, and Alembic migrations run programmatically at startup.

### proxy/
The multi-format parser, deduplicator (by `protocol://host:port` identity), and
the explainable quality scorer.

### discovery/
`DiscoveryProvider` interface, a manager/registry, importer, normalizer,
scheduler, and providers (file, feed, API, custom, internet). Providers only
*produce candidates*; none validate.

### testing/ (validation)
The async `validate_proxy` (httpx for HTTP/HTTPS/SOCKS5, aiohttp-socks for
SOCKS4), the concurrent `ValidationEngine` with `JobControl` (pause/resume/stop),
validation profiles, and anonymity/DNS analysis.

### intelligence/
`IntelligenceProvider` interface, a merging manager, geo/asn/isp helpers, the
evidence-based `NetworkClassifier`, and providers (ip-api, ipinfo, offline
builtin).

### services/
The orchestration `ProcessingPipeline` (validation -> intelligence ->
classification -> quality -> batched persistence), the global `JobManager`, the
monitoring service, exporters, the credential cipher, the `AppContext`, and the
`bootstrap` startup sequence.

### workers/
`AsyncWorker` runs an asyncio loop inside a `QThread` and emits Qt signals.
`ValidationWorker`, `DiscoveryWorker`, `MonitoringWorker` and `ExportWorker`
keep all network/DB work off the GUI thread.

### ui/
Centralized themes, the `QMainWindow` with sidebar + `QStackedWidget`, the 11
pages, reusable widgets (charts, stat cards, empty states, toasts, filter bar),
dialogs, and the DB-backed paginated `ProxyTableModel`.

## The pipeline

```
Discovery -> Normalize -> Deduplicate -> (queue)
          -> Validate (protocol detect, connect, proxied request, exit IP)
          -> Intelligence (geo/ASN/ISP/hosting)
          -> Classify (evidence-based)
          -> Quality score (explainable)
          -> Persist (identity upsert, tests, history)
          -> Filter / Monitor / Export
```

Fault tolerance is a first-class concern: a single failed proxy or provider is
caught and recorded, never propagated to abort the batch.

## Threading model

- The GUI thread never performs blocking network or database work.
- Each job runs in a dedicated `QThread` hosting its own asyncio event loop.
- Concurrency inside a job is bounded by an `asyncio.Semaphore` (no thread per
  proxy).
- Pause/resume/stop use thread-safe `threading.Event` flags polled by the async
  workers.
