from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    AssignmentStatus,
    AuditEvent,
    Document,
    DocumentReviewAssignment,
    DocumentStatus,
    DocumentVersion,
    DocumentWorkflow,
    ReviewAction,
    ReviewActionChoice,
    WorkflowStatus,
)


def create_audit_event(document, event_type, message, actor=None, document_version=None, metadata=None):
    return AuditEvent.objects.create(
        organization=document.organization,
        document=document,
        document_version=document_version,
        actor=actor,
        event_type=event_type,
        message=message,
        metadata=metadata or {},
    )


@transaction.atomic
def submit_document(*, actor, template, payload):
    file_data = payload["file"]
    now = timezone.now()

    document = Document.objects.create(
        organization=actor.organization,
        submitter=actor,
        title=payload["title"],
        description=payload.get("description", ""),
        status=DocumentStatus.IN_REVIEW,
    )
    version = DocumentVersion.objects.create(
        document=document,
        version_number=1,
        file_name=file_data["file_name"],
        file_uri=file_data["file_uri"],
        mime_type=file_data["mime_type"],
        file_size_bytes=file_data["file_size_bytes"],
        submitted_by=actor,
        change_summary=payload.get("change_summary", ""),
    )
    document.current_version = version
    document.save(update_fields=["current_version", "updated_at"])

    first_stage = template.steps.order_by("stage_number").first().stage_number
    workflow = DocumentWorkflow.objects.create(
        document=document,
        workflow_template=template,
        approval_mode=template.approval_mode,
        status=WorkflowStatus.IN_REVIEW,
        current_stage_number=first_stage,
        started_at=now,
    )

    assignments = []
    for step in template.steps.select_related("reviewer").order_by("stage_number", "step_order"):
        is_active = step.stage_number == first_stage
        assignments.append(
            DocumentReviewAssignment(
                document_workflow=workflow,
                document_version=version,
                reviewer=step.reviewer,
                stage_number=step.stage_number,
                step_order=step.step_order,
                status=AssignmentStatus.ACTIVE if is_active else AssignmentStatus.PENDING,
                activated_at=now if is_active else None,
                due_at=now + timedelta(hours=step.due_in_hours) if is_active and step.due_in_hours else None,
            )
        )
    DocumentReviewAssignment.objects.bulk_create(assignments)

    create_audit_event(document, "document.submitted", "Document submitted for approval.", actor, version)
    create_audit_event(
        document,
        "workflow.started",
        f"Workflow '{template.name}' started.",
        actor,
        version,
        {"workflow_template_id": str(template.id), "approval_mode": template.approval_mode},
    )
    active_count = workflow.assignments.filter(status=AssignmentStatus.ACTIVE).count()
    create_audit_event(
        document,
        "review.assignment_activated",
        f"Stage {first_stage} activated for {active_count} reviewer(s).",
        None,
        version,
        {"stage_number": first_stage, "assignment_count": active_count},
    )
    return document, workflow


@transaction.atomic
def record_review_action(*, actor, document, payload):
    try:
        assignment = (
            DocumentReviewAssignment.objects.select_for_update()
            .select_related("document_workflow", "document_version", "reviewer")
            .get(id=payload["assignment_id"], document_workflow__document=document)
        )
    except DocumentReviewAssignment.DoesNotExist as exc:
        raise ValidationError({"assignment_id": "Review assignment not found for this document."}) from exc

    if assignment.reviewer_id != actor.id:
        raise PermissionDenied("Only the assigned reviewer can act on this assignment.")
    if assignment.status != AssignmentStatus.ACTIVE:
        raise ValidationError({"assignment_id": "This review assignment is not currently active."})
    if hasattr(assignment, "review_action"):
        raise ValidationError({"assignment_id": "A final review action already exists for this assignment."})

    action = ReviewAction.objects.create(
        assignment=assignment,
        document=document,
        document_version=assignment.document_version,
        reviewer=actor,
        action=payload["action"],
        comment=payload.get("comment", ""),
    )

    now = timezone.now()
    workflow = assignment.document_workflow

    if action.action == ReviewActionChoice.REJECT:
        assignment.status = AssignmentStatus.REJECTED
        assignment.completed_at = now
        assignment.save(update_fields=["status", "completed_at", "updated_at"])
        workflow.status = WorkflowStatus.REJECTED
        workflow.completed_at = now
        workflow.save(update_fields=["status", "completed_at", "updated_at"])
        document.status = DocumentStatus.REJECTED
        document.save(update_fields=["status", "updated_at"])
        workflow.assignments.filter(status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.PENDING]).exclude(
            id=assignment.id
        ).update(status=AssignmentStatus.CANCELLED, updated_at=now)
        create_audit_event(
            document,
            "review.rejected",
            f"{actor.full_name} rejected version {assignment.document_version.version_number}.",
            actor,
            assignment.document_version,
            {"assignment_id": str(assignment.id), "comment": action.comment},
        )
        create_audit_event(document, "workflow.rejected", "Workflow rejected and returned to submitter.", None, assignment.document_version)
        return action, workflow

    assignment.status = AssignmentStatus.APPROVED
    assignment.completed_at = now
    assignment.save(update_fields=["status", "completed_at", "updated_at"])
    create_audit_event(
        document,
        "review.approved",
        f"{actor.full_name} approved version {assignment.document_version.version_number}.",
        actor,
        assignment.document_version,
        {"assignment_id": str(assignment.id), "comment": action.comment},
    )

    current_stage = workflow.current_stage_number
    current_stage_open = workflow.assignments.filter(
        stage_number=current_stage,
        status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.PENDING],
    ).exists()
    if current_stage_open:
        return action, workflow

    next_assignment = workflow.assignments.filter(status=AssignmentStatus.PENDING).order_by("stage_number").first()
    if next_assignment:
        next_stage = next_assignment.stage_number
        workflow.current_stage_number = next_stage
        workflow.save(update_fields=["current_stage_number", "updated_at"])
        activated = workflow.assignments.filter(stage_number=next_stage, status=AssignmentStatus.PENDING)
        activated.update(status=AssignmentStatus.ACTIVE, activated_at=now, updated_at=now)
        create_audit_event(
            document,
            "review.assignment_activated",
            f"Stage {next_stage} activated for {activated.count()} reviewer(s).",
            None,
            assignment.document_version,
            {"stage_number": next_stage, "assignment_count": activated.count()},
        )
        return action, workflow

    workflow.status = WorkflowStatus.APPROVED
    workflow.completed_at = now
    workflow.save(update_fields=["status", "completed_at", "updated_at"])
    document.status = DocumentStatus.APPROVED
    document.save(update_fields=["status", "updated_at"])
    create_audit_event(document, "workflow.approved", "All required reviewers approved the document.", None, assignment.document_version)
    return action, workflow
