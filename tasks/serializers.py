from rest_framework import serializers
from .models import Task


class SubtaskSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'completed',
            'due_date',
            'priority',
            'recurrence',
            'parent',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    title = serializers.CharField(
        error_messages={
            'blank': 'must not be empty',
            'required': 'must not be empty',
        }
    )
    description = serializers.CharField(
        error_messages={
            'blank': 'must not be empty',
            'required': 'must not be empty',
        }
    )
    completed = serializers.BooleanField(
        default=False,
        error_messages={
            'invalid': 'must be a boolean'
        }
    )
    due_date = serializers.DateField(
        required=False,
        allow_null=True,
        error_messages={
            'invalid': 'must be a real YYYY-MM-DD date'
        }
    )
    priority = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        default='medium',
        error_messages={
            'invalid_choice': 'must be one of low, medium, high'
        }
    )
    recurrence = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    subtasks = SubtaskSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'completed',
            'due_date',
            'priority',
            'recurrence',
            'parent',
            'created_at',
            'updated_at',
            'subtasks',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'subtasks']

    def validate_title(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("must not be empty")
        return value.strip()

    def validate_description(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("must not be empty")
        return value.strip()

    def validate_completed(self, value):
        if not isinstance(value, bool):
            raise serializers.ValidationError("must be a boolean")
        return value

    def validate_priority(self, value):
        if value not in ('low', 'medium', 'high'):
            raise serializers.ValidationError("must be one of low, medium, high")
        return value

    def validate(self, attrs):
        # A task that is itself a subtask cannot be given subtasks
        parent = attrs.get('parent')
        if parent and parent.parent_id is not None:
            raise serializers.ValidationError({"parent": "A subtask cannot be given subtasks"})
        return attrs
