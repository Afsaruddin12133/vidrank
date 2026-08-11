"""Wrangler worker entrypoint — thin FastAPI → Cloudflare bridge. (v2.0.1 - Subscriptions active)

Cloudflare executes the `main` file as a top-level module (no parent package),
so app/main.py's relative imports (`from . import cache`) cannot resolve when
main.py itself is the entrypoint. This module imports the `app` package
absolutely, builds the FastAPI app, and presents the worker handler as
`Default` (the class name wrangler statically detects).
"""
from workers import WorkerEntrypoint  # type: ignore

from app import db, mq  # for the BatchedFlusher teardown and queue consumer
from app.main import app
from app.quotas import QuotaDO  # noqa: F401  (exported for wrangler DO bindings)
from app.ratestate import RateStateDO  # noqa: F401

# Re-export as module-level names so the worker runtime / API reconciliation
# can statically resolve the Durable Object classes declared in wrangler.toml.
QuotaDO = QuotaDO  # noqa: PLW0127
RateStateDO = RateStateDO  # noqa: PLW0127


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        app.state.env = self.env
        app.state.flusher = db.BatchedFlusher(self.env)
        import asgi

        resp = await asgi.fetch(app, request.js_object, self.env)
        await app.state.flusher.aclose()
        return resp
    
    async def queue(self, batch):
        """Queue consumer: process batched jobs from FREE_QUEUE and PRO_QUEUE."""
        for message in batch.messages:
            try:
                payload = message.body
                # Execute the queued request
                result = await mq.consume_job(self.env, payload)
                
                # Mark as complete (ack)
                message.ack()
            except Exception as e:
                # Retry on failure (up to max_retries configured in wrangler.toml)
                message.retry()
