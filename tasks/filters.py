import django_filters
from .models import Task


class TaskFilter(django_filters.FilterSet):
    is_parent = django_filters.BooleanFilter(field_name='parent', lookup_expr='isnull')
    due_date = django_filters.DateFilter(field_name='due_date')
    due_date__gte = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_date__lte = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = Task
        fields = ['completed', 'priority', 'due_date', 'parent', 'is_parent']
