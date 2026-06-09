import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    SUBMITTER = "submitter", "Submitter"
    REVIEWER = "reviewer", "Reviewer"


class User(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="users")
    email = models.EmailField()
    full_name = models.CharField(max_length=200)
    role = models.CharField(max_length=30, choices=UserRole.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "email"], name="unique_user_email_per_org"),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    IN_REVIEW = "in_review", "In review"
    REJECTED = "rejected", "Rejected"
    APPROVED = "approved", "Approved"
    CANCELLED = "cancelled", "Cancelled"


class Document(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="documents")
    submitter = models.ForeignKey(User, on_delete=models.PROTECT, related_name="submitted_documents")
    current_version = models.ForeignKey(
        "DocumentVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["submitter", "created_at"]),
        ]

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    file_name = models.CharField(max_length=255)
    file_uri = models.TextField()
    mime_type = models.CharField(max_length=100)
    file_size_bytes = models.PositiveBigIntegerField()
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="submitted_versions")
    change_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "version_number"], name="unique_document_version_number"),
        ]

    def __str__(self):
        return f"{self.document_id} v{self.version_number}"


class ApprovalMode(models.TextChoices):
    SEQUENTIAL = "sequential", "Sequential"
    PARALLEL = "parallel", "Parallel"


class WorkflowTemplate(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="workflow_templates")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    approval_mode = models.CharField(max_length=30, choices=ApprovalMode.choices, default=ApprovalMode.SEQUENTIAL)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_workflow_templates")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_workflow_template_name_per_org"),
        ]

    def __str__(self):
        return self.name


class WorkflowStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_template = models.ForeignKey(WorkflowTemplate, on_delete=models.CASCADE, related_name="steps")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="workflow_steps")
    stage_number = models.PositiveIntegerField()
    step_order = models.PositiveIntegerField()
    is_required = models.BooleanField(default=True)
    due_in_hours = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["stage_number", "step_order"]
        constraints = [
            models.UniqueConstraint(fields=["workflow_template", "step_order"], name="unique_step_order_per_template"),
            models.UniqueConstraint(
                fields=["workflow_template", "reviewer", "stage_number"],
                name="unique_reviewer_per_template_stage",
            ),
        ]

    def __str__(self):
        return f"{self.workflow_template.name}: stage {self.stage_number}, order {self.step_order}"


class WorkflowStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    IN_REVIEW = "in_review", "In review"
    REJECTED = "rejected", "Rejected"
    APPROVED = "approved", "Approved"
    CANCELLED = "cancelled", "Cancelled"


class DocumentWorkflow(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="workflow")
    workflow_template = models.ForeignKey(WorkflowTemplate, on_delete=models.PROTECT, related_name="document_workflows")
    approval_mode = models.CharField(max_length=30, choices=ApprovalMode.choices)
    status = models.CharField(max_length=30, choices=WorkflowStatus.choices, default=WorkflowStatus.NOT_STARTED)
    current_stage_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.document.title} workflow"


class AssignmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SKIPPED = "skipped", "Skipped"
    CANCELLED = "cancelled", "Cancelled"


class DocumentReviewAssignment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_workflow = models.ForeignKey(DocumentWorkflow, on_delete=models.CASCADE, related_name="assignments")
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="review_assignments")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="review_assignments")
    stage_number = models.PositiveIntegerField()
    step_order = models.PositiveIntegerField()
    status = models.CharField(max_length=30, choices=AssignmentStatus.choices, default=AssignmentStatus.PENDING)
    activated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["stage_number", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_workflow", "reviewer", "document_version", "stage_number"],
                name="unique_assignment_reviewer_version_stage",
            ),
            models.UniqueConstraint(
                fields=["document_workflow", "step_order", "document_version"],
                name="unique_assignment_order_per_workflow_version",
            ),
        ]

    def __str__(self):
        return f"{self.reviewer.full_name} on {self.document_workflow.document.title}"


class ReviewActionChoice(models.TextChoices):
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"


class ReviewAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.OneToOneField(DocumentReviewAssignment, on_delete=models.CASCADE, related_name="review_action")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="review_actions")
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="review_actions")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="review_actions")
    action = models.CharField(max_length=30, choices=ReviewActionChoice.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reviewer.full_name} {self.action} {self.document.title}"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="audit_events")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="audit_events")
    document_version = models.ForeignKey(
        DocumentVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    event_type = models.CharField(max_length=50)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["document", "created_at"]),
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.document.title}"
