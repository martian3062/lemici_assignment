from django.core.management.base import BaseCommand

from approvals.models import (
    ApprovalMode,
    Organization,
    User,
    UserRole,
    WorkflowStep,
    WorkflowTemplate,
)


class Command(BaseCommand):
    help = "Create demo FlowDesk users and workflow templates."

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(name="Demo Organization")

        submitter, _ = User.objects.get_or_create(
            organization=org,
            email="submitter@example.com",
            defaults={"full_name": "Submitter User", "role": UserRole.SUBMITTER},
        )
        admin, _ = User.objects.get_or_create(
            organization=org,
            email="admin@example.com",
            defaults={"full_name": "Admin User", "role": UserRole.ADMIN},
        )
        reviewer_1, _ = User.objects.get_or_create(
            organization=org,
            email="reviewer1@example.com",
            defaults={"full_name": "Reviewer One", "role": UserRole.REVIEWER},
        )
        reviewer_2, _ = User.objects.get_or_create(
            organization=org,
            email="reviewer2@example.com",
            defaults={"full_name": "Reviewer Two", "role": UserRole.REVIEWER},
        )

        sequential, _ = WorkflowTemplate.objects.get_or_create(
            organization=org,
            name="Sequential Legal + Finance",
            defaults={
                "description": "Two reviewers in sequence.",
                "approval_mode": ApprovalMode.SEQUENTIAL,
                "created_by": admin,
            },
        )
        parallel, _ = WorkflowTemplate.objects.get_or_create(
            organization=org,
            name="Parallel Legal + Finance",
            defaults={
                "description": "Two reviewers at the same time.",
                "approval_mode": ApprovalMode.PARALLEL,
                "created_by": admin,
            },
        )

        if not sequential.steps.exists():
            WorkflowStep.objects.create(workflow_template=sequential, reviewer=reviewer_1, stage_number=1, step_order=1)
            WorkflowStep.objects.create(workflow_template=sequential, reviewer=reviewer_2, stage_number=2, step_order=2)

        if not parallel.steps.exists():
            WorkflowStep.objects.create(workflow_template=parallel, reviewer=reviewer_1, stage_number=1, step_order=1)
            WorkflowStep.objects.create(workflow_template=parallel, reviewer=reviewer_2, stage_number=1, step_order=2)

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Submitter X-User-Id: {submitter.id}")
        self.stdout.write(f"Reviewer One X-User-Id: {reviewer_1.id}")
        self.stdout.write(f"Reviewer Two X-User-Id: {reviewer_2.id}")
        self.stdout.write(f"Sequential workflow_template_id: {sequential.id}")
        self.stdout.write(f"Parallel workflow_template_id: {parallel.id}")
