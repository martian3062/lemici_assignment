from django.contrib import admin

from .models import (
    AuditEvent,
    Document,
    DocumentReviewAssignment,
    DocumentVersion,
    DocumentWorkflow,
    Organization,
    ReviewAction,
    User,
    WorkflowStep,
    WorkflowTemplate,
)


@admin.register(Organization, User, Document, DocumentVersion, WorkflowTemplate, WorkflowStep, DocumentWorkflow, DocumentReviewAssignment, ReviewAction, AuditEvent)
class DefaultAdmin(admin.ModelAdmin):
    pass
