# TraceMemory Recovery Worker

This directory contains the enterprise worker foundation. The current API exposes database-backed `background_jobs` endpoints so enterprises can run a worker process that:

- scans interrupted runs,
- leases retry jobs,
- restores checkpoints,
- resumes safe workflows,
- moves unsafe runs to manual review,
- writes recovery audit records.

A production deployment can implement this worker with SQS, Temporal, Celery, BullMQ, Kubernetes Jobs, or the database-backed queue contract already exposed by `/api/enterprise/jobs`.
