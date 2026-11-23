from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'completed', 'priority', 'due_date', 'parent', 'created_at')
    list_filter = ('completed', 'priority', 'due_date')
    search_fields = ('title', 'description')
    ordering = ('-created_at',)
