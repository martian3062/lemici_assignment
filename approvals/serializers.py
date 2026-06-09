from rest_framework import serializers

from .models import (
    AssignmentStatus,
    AuditEvent,
    Document,
    DocumentReviewAssignment,
    DocumentVersion,
    DocumentWorkflow,
    ReviewActionChoice,
    User,
    WorkflowTemplate,
)


class FileSubmissionSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    file_uri = serializers.CharField()
    mime_type = serializers.CharField(max_length=100)
    file_size_bytes = serializers.IntegerField(min_value=1)


class SubmitDocumentSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    workflow_template_id = serializers.UUIDField()
    file = FileSubmissionSerializer()
    change_summary = serializers.CharField(required=False, allow_blank=True)

    def validate_workflow_template_id(self, value):
        actor = self.context["actor"]
        try:
            template = WorkflowTemplate.objects.get(id=value, organization=actor.organization)
        except WorkflowTemplate.DoesNotExist as exc:
            raise serializers.ValidationError("The selected workflow template does not exist.") from exc
        if not template.is_active:
            raise serializers.ValidationError("The selected workflow template is inactive.")
        if not template.steps.exists():
            raise serializers.ValidationError("The selected workflow template has no reviewers.")
        self.context["workflow_template"] = template
        return value


class ReviewActionSerializer(serializers.Serializer):
    assignment_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=ReviewActionChoice.choices)
    comment = serializers.CharField(required=False, allow_blank=True)


class ActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name"]


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = [
            "id",
            "version_number",
            "file_name",
            "file_uri",
            "mime_type",
            "file_size_bytes",
            "change_summary",
            "created_at",
        ]


class DocumentSerializer(serializers.ModelSerializer):
    submitter_id = serializers.UUIDField(source="submitter.id", read_only=True)
    current_version_id = serializers.UUIDField(source="current_version.id", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "description",
            "status",
            "submitter_id",
            "current_version_id",
            "created_at",
            "updated_at",
        ]


class WorkflowSerializer(serializers.ModelSerializer):
    workflow_template_id = serializers.UUIDField(source="workflow_template.id", read_only=True)

    class Meta:
        model = DocumentWorkflow
        fields = [
            "id",
            "workflow_template_id",
            "approval_mode",
            "status",
            "current_stage_number",
            "started_at",
            "completed_at",
        ]


class AssignmentSerializer(serializers.ModelSerializer):
    reviewer_id = serializers.UUIDField(source="reviewer.id", read_only=True)
    document_version_id = serializers.UUIDField(source="document_version.id", read_only=True)

    class Meta:
        model = DocumentReviewAssignment
        fields = [
            "id",
            "document_version_id",
            "reviewer_id",
            "stage_number",
            "step_order",
            "status",
            "activated_at",
            "completed_at",
            "due_at",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    actor = ActorSerializer(read_only=True)
    document_version_id = serializers.UUIDField(source="document_version.id", read_only=True, allow_null=True)

    class Meta:
        model = AuditEvent
        fields = ["id", "event_type", "message", "actor", "document_version_id", "metadata", "created_at"]


class ReviewResponseSerializer(serializers.Serializer):
    review_action = serializers.DictField()
    document = DocumentSerializer()
    workflow = WorkflowSerializer()
    active_assignments = AssignmentSerializer(many=True)
    remaining_required_approvals = serializers.IntegerField()


def active_assignments_for(workflow):
    return workflow.assignments.filter(status=AssignmentStatus.ACTIVE).select_related("reviewer", "document_version")
