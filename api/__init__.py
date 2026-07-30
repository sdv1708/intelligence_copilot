"""HTTP layer over the copilot.

`api.main:app` is the ASGI application. Everything the browser can do goes
through the routers in `api.routes`, which are thin: they validate input, call
one method on the shared `CopilotOrchestrator`, and translate the result into
the response models in `api.schemas`. No orchestration logic lives here.
"""
