from django.db import transaction
from django.http import Http404
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer, SubtaskSummarySerializer
from .filters import TaskFilter
from .errors import error_response, format_serializer_errors
from .ai import parse_task_text, break_down_task, call_llm_parser
from .idempotency import handle_idempotent_request


class TaskViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for Task entity supporting:
    - Standard CRUD with consistent error response format
    - Natural language task parsing (/api/tasks/from-text/)
    - Subtasks creation & listing (/api/tasks/{id}/subtasks/)
    - Task breakdown (/api/tasks/{id}/breakdown/)
    - Idempotent creation via 'Idempotency-Key' header
    - Filtering, search, ordering, and pagination
    """
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    filterset_class = TaskFilter
    search_fields = ['title', 'description']
    ordering_fields = ['due_date', 'created_at', 'priority', 'title']
    ordering = ['-created_at']

    def get_object(self):
        try:
            return super().get_object()
        except (Http404, Task.DoesNotExist):
            return None

    def create(self, request, *args, **kwargs):
        def _execute():
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                return error_response(
                    code="VALIDATION_ERROR",
                    message="Validation failed",
                    details=format_serializer_errors(serializer.errors),
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return handle_idempotent_request(request, _execute)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return error_response(
                code="NOT_FOUND",
                message="Task not found",
                details=[],
                status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if instance is None:
            return error_response(
                code="NOT_FOUND",
                message="Task not found",
                details=[],
                status_code=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="Validation failed",
                details=format_serializer_errors(serializer.errors),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return error_response(
                code="NOT_FOUND",
                message="Task not found",
                details=[],
                status_code=status.HTTP_404_NOT_FOUND
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='from-text')
    def from_text(self, request):
        """Creates a task from natural language text."""
        def _execute():
            raw_text = request.data.get('text')
            if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
                return error_response(
                    code="VALIDATION_ERROR",
                    message="Validation failed",
                    details=[{"field": "text", "issue": "must not be empty"}],
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Check optional LLM wrapper mode
            use_llm = request.data.get('use_llm', False)
            if use_llm:
                if not getattr(settings, 'LLM_API_KEY', None):
                    return error_response(
                        code="SERVICE_UNAVAILABLE",
                        message="LLM API key not configured",
                        details=[],
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                try:
                    parsed_dict = call_llm_parser(raw_text)
                except Exception as exc:
                    return error_response(
                        code="PARSER_ERROR",
                        message=f"LLM parsing failed: {str(exc)}",
                        details=[],
                        status_code=status.HTTP_502_BAD_GATEWAY
                    )
            else:
                try:
                    parsed_dict = parse_task_text(raw_text)
                except Exception as exc:
                    return error_response(
                        code="PARSER_ERROR",
                        message=f"Parser raised exception: {str(exc)}",
                        details=[],
                        status_code=status.HTTP_502_BAD_GATEWAY
                    )

            # Never trust output: validate through TaskSerializer
            serializer = TaskSerializer(data=parsed_dict)
            if not serializer.is_valid():
                return error_response(
                    code="PARSER_VALIDATION_ERROR",
                    message="Generated task failed validation",
                    details=format_serializer_errors(serializer.errors),
                    status_code=status.HTTP_502_BAD_GATEWAY
                )

            task = serializer.save()
            return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

        return handle_idempotent_request(request, _execute)

    @action(detail=True, methods=['get', 'post'], url_path='subtasks')
    def subtasks(self, request, pk=None):
        """GET lists a task's subtasks; POST creates one subtask for this task."""
        parent_task = self.get_object()
        if parent_task is None:
            return error_response(
                code="NOT_FOUND",
                message="Task not found",
                details=[],
                status_code=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            subtasks = parent_task.subtasks.all()
            return Response(SubtaskSummarySerializer(subtasks, many=True).data)

        # POST - create subtask
        # Rule: A task that is itself a subtask cannot be given subtasks
        if parent_task.parent_id is not None:
            return error_response(
                code="INVALID_SUBTASK",
                message="A task that is itself a subtask cannot be given subtasks",
                details=[{"field": "parent", "issue": "cannot nest subtasks beyond 1 level"}],
                status_code=status.HTTP_400_BAD_REQUEST
            )

        payload = request.data.copy()
        payload['parent'] = parent_task.id
        serializer = TaskSerializer(data=payload)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="Validation failed",
                details=format_serializer_errors(serializer.errors),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        subtask = serializer.save(parent=parent_task)
        return Response(TaskSerializer(subtask).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='breakdown')
    def breakdown(self, request, pk=None):
        """Breaks down a task into multiple subtasks atomically."""
        def _execute():
            task = self.get_object()
            if task is None:
                return error_response(
                    code="NOT_FOUND",
                    message="Task not found",
                    details=[],
                    status_code=status.HTTP_404_NOT_FOUND
                )

            # Rule: A task that is itself a subtask cannot be broken down
            if task.parent_id is not None:
                return error_response(
                    code="INVALID_BREAKDOWN",
                    message="A task that is itself a subtask cannot be broken down",
                    details=[{"field": "parent", "issue": "subtask cannot be broken down"}],
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            try:
                subtask_dicts = break_down_task(task)
            except Exception as exc:
                return error_response(
                    code="BREAKDOWN_ERROR",
                    message=f"Breakdown failed: {str(exc)}",
                    details=[],
                    status_code=status.HTTP_502_BAD_GATEWAY
                )

            # All-or-nothing: Validate every item first
            serializers_to_save = []
            for item in subtask_dicts:
                item_payload = item.copy()
                item_payload['parent'] = task.id
                serializer = TaskSerializer(data=item_payload)
                if not serializer.is_valid():
                    return error_response(
                        code="VALIDATION_ERROR",
                        message="One or more breakdown items failed validation",
                        details=format_serializer_errors(serializer.errors),
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                serializers_to_save.append(serializer)

            # Save all atomically
            with transaction.atomic():
                saved_subtasks = [s.save(parent=task) for s in serializers_to_save]

            return Response(
                SubtaskSummarySerializer(saved_subtasks, many=True).data,
                status=status.HTTP_201_CREATED
            )

        return handle_idempotent_request(request, _execute)
