import copy
from rest_framework.response import Response
from .errors import error_response

# In-memory store: {key: {"body": ..., "response_data": ..., "status_code": ...}}
IDEMPOTENCY_STORE = {}


def handle_idempotent_request(request, execute_func):
    """
    Handles idempotency via the 'Idempotency-Key' request header.
    - Same key and same body: returns the stored response.
    - Same key with a different body: returns 422 IDEMPOTENCY_CONFLICT error.
    - No key provided: executes normally.
    - New key: executes, caches successful response (2xx), and returns it.
    """
    key = request.headers.get("Idempotency-Key")
    if not key:
        return execute_func()

    if key in IDEMPOTENCY_STORE:
        stored = IDEMPOTENCY_STORE[key]
        if stored["body"] == request.data:
            return Response(stored["response_data"], status=stored["status_code"])
        else:
            return error_response(
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key already used with a different request body",
                details=[],
                status_code=422
            )

    response = execute_func()

    # Store only successful responses so failed requests can be retried with the same key
    if 200 <= response.status_code < 300:
        IDEMPOTENCY_STORE[key] = {
            "body": copy.deepcopy(request.data),
            "response_data": copy.deepcopy(response.data),
            "status_code": response.status_code,
        }

    return response
