from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AssignmentStatus, AuditEvent, Document, User
from .serializers import (
    AssignmentSerializer,
    AuditEventSerializer,
    DocumentSerializer,
    ReviewActionSerializer,
    SubmitDocumentSerializer,
    WorkflowSerializer,
    active_assignments_for,
)
from .services import record_review_action, submit_document


def get_actor(request):
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise PermissionDenied("Missing X-User-Id header.")
    try:
        return User.objects.select_related("organization").get(id=user_id, is_active=True)
    except User.DoesNotExist as exc:
        raise PermissionDenied("Invalid or inactive X-User-Id.") from exc


class SubmitDocumentView(APIView):
    def post(self, request):
        actor = get_actor(request)
        serializer = SubmitDocumentSerializer(data=request.data, context={"actor": actor})
        serializer.is_valid(raise_exception=True)
        document, workflow = submit_document(
            actor=actor,
            template=serializer.context["workflow_template"],
            payload=serializer.validated_data,
        )
        return Response(
            {
                "document": DocumentSerializer(document).data,
                "workflow": WorkflowSerializer(workflow).data,
                "active_assignments": AssignmentSerializer(active_assignments_for(workflow), many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ReviewActionView(APIView):
    def post(self, request, document_id):
        actor = get_actor(request)
        try:
            document = Document.objects.select_related("organization").get(id=document_id, organization=actor.organization)
        except Document.DoesNotExist as exc:
            raise NotFound("Document not found.") from exc

        serializer = ReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action, workflow = record_review_action(actor=actor, document=document, payload=serializer.validated_data)
        active_assignments = active_assignments_for(workflow)
        remaining = workflow.assignments.filter(status=AssignmentStatus.ACTIVE).count()
        return Response(
            {
                "review_action": {
                    "id": str(action.id),
                    "assignment_id": str(action.assignment_id),
                    "document_id": str(action.document_id),
                    "document_version_id": str(action.document_version_id),
                    "reviewer_id": str(action.reviewer_id),
                    "action": action.action,
                    "comment": action.comment,
                    "created_at": action.created_at,
                },
                "document": DocumentSerializer(document).data,
                "workflow": WorkflowSerializer(workflow).data,
                "active_assignments": AssignmentSerializer(active_assignments, many=True).data,
                "remaining_required_approvals": remaining,
            }
        )


class TimelineView(APIView):
    def get(self, request, document_id):
        actor = get_actor(request)
        try:
            document = Document.objects.select_related("current_version").get(id=document_id, organization=actor.organization)
        except Document.DoesNotExist as exc:
            raise NotFound("Document not found.") from exc

        events = AuditEvent.objects.select_related("actor", "document_version").filter(document=document)
        event_type = request.query_params.get("event_type")
        if event_type:
            events = events.filter(event_type=event_type)
        include_metadata = request.query_params.get("include_metadata", "false").lower() == "true"
        data = AuditEventSerializer(events, many=True).data
        if not include_metadata:
            for event in data:
                event.pop("metadata", None)
        return Response({"document": DocumentSerializer(document).data, "timeline": data})


class ErrorExampleMixin:
    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if response is not None and isinstance(exc, ValidationError):
            response.data = {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": response.data,
                }
            }
        return response
