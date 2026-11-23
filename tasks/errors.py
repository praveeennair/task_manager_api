from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException


def error_response(code: str, message: str, details=None, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    """Returns a standardized JSON error response."""
    return Response(
        {
            "error": {
                "code": str(code),
                "message": str(message),
                "details": details if details is not None else []
            }
        },
        status=status_code
    )


def format_serializer_errors(errors) -> list:
    """Converts DRF serializer.errors dictionary into details list: [{'field': ..., 'issue': ...}]."""
    details = []
    if isinstance(errors, dict):
        for field, messages in errors.items():
            if isinstance(messages, list):
                for msg in messages:
                    details.append({"field": str(field), "issue": str(msg)})
            elif isinstance(messages, dict):
                nested = format_serializer_errors(messages)
                for item in nested:
                    details.append({"field": f"{field}.{item['field']}", "issue": item['issue']})
            else:
                details.append({"field": str(field), "issue": str(messages)})
    elif isinstance(errors, list):
        for err in errors:
            if isinstance(err, dict):
                details.extend(format_serializer_errors(err))
            else:
                details.append({"field": "non_field_errors", "issue": str(err)})
    return details


def custom_exception_handler(exc, context):
    """Custom exception handler ensuring any DRF exception matches the standard error response shape."""
    response = exception_handler(exc, context)

    if response is not None:
        status_code = response.status_code
        if status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
            message = "Task not found"
            details = []
        elif status_code == status.HTTP_400_BAD_REQUEST:
            code = "VALIDATION_ERROR"
            message = "Validation failed"
            details = format_serializer_errors(response.data) if isinstance(response.data, (dict, list)) else []
        elif status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "METHOD_NOT_ALLOWED"
            message = str(response.data.get('detail', 'Method not allowed'))
            details = []
        elif status_code == 422:
            code = "UNPROCESSABLE_ENTITY"
            message = "Unprocessable entity"
            details = []
        else:
            code = "ERROR"
            message = str(response.data.get('detail', 'An error occurred'))
            details = []

        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": details
            }
        }

    return response
