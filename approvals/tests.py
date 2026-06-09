from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import (
    ApprovalMode,
    AssignmentStatus,
    DocumentStatus,
    Organization,
    User,
    UserRole,
    WorkflowStep,
    WorkflowTemplate,
)


class FlowDeskApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Acme")
        self.submitter = User.objects.create(
            organization=self.org,
            email="submitter@example.com",
            full_name="Submitter User",
            role=UserRole.SUBMITTER,
        )
        self.reviewer_1 = User.objects.create(
            organization=self.org,
            email="reviewer1@example.com",
            full_name="Reviewer One",
            role=UserRole.REVIEWER,
        )
        self.reviewer_2 = User.objects.create(
            organization=self.org,
            email="reviewer2@example.com",
            full_name="Reviewer Two",
            role=UserRole.REVIEWER,
        )
        self.admin = User.objects.create(
            organization=self.org,
            email="admin@example.com",
            full_name="Admin User",
            role=UserRole.ADMIN,
        )

    def auth(self, user):
        return {"HTTP_X_USER_ID": str(user.id)}

    def create_template(self, approval_mode=ApprovalMode.SEQUENTIAL):
        template = WorkflowTemplate.objects.create(
            organization=self.org,
            name=f"{approval_mode} template",
            approval_mode=approval_mode,
            created_by=self.admin,
        )
        if approval_mode == ApprovalMode.SEQUENTIAL:
            WorkflowStep.objects.create(
                workflow_template=template,
                reviewer=self.reviewer_1,
                stage_number=1,
                step_order=1,
            )
            WorkflowStep.objects.create(
                workflow_template=template,
                reviewer=self.reviewer_2,
                stage_number=2,
                step_order=2,
            )
        else:
            WorkflowStep.objects.create(
                workflow_template=template,
                reviewer=self.reviewer_1,
                stage_number=1,
                step_order=1,
            )
            WorkflowStep.objects.create(
                workflow_template=template,
                reviewer=self.reviewer_2,
                stage_number=1,
                step_order=2,
            )
        return template

    def submit_document(self, template):
        payload = {
            "title": "Vendor Contract",
            "description": "Needs approval.",
            "workflow_template_id": str(template.id),
            "file": {
                "file_name": "contract.pdf",
                "file_uri": "s3://demo/contract.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 12345,
            },
            "change_summary": "Initial submission",
        }
        return self.client.post(reverse("submit-document"), payload, format="json", **self.auth(self.submitter))

    def test_submit_document_starts_sequential_workflow(self):
        template = self.create_template()

        response = self.submit_document(template)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["document"]["status"], DocumentStatus.IN_REVIEW)
        self.assertEqual(response.data["workflow"]["approval_mode"], ApprovalMode.SEQUENTIAL)
        self.assertEqual(len(response.data["active_assignments"]), 1)
        self.assertEqual(response.data["active_assignments"][0]["reviewer_id"], str(self.reviewer_1.id))

    def test_sequential_review_activates_next_stage_then_approves(self):
        template = self.create_template()
        submit_response = self.submit_document(template)
        document_id = submit_response.data["document"]["id"]
        first_assignment = submit_response.data["active_assignments"][0]["id"]

        first_action = self.client.post(
            reverse("review-action", args=[document_id]),
            {"assignment_id": first_assignment, "action": "approve", "comment": "Looks good."},
            format="json",
            **self.auth(self.reviewer_1),
        )

        self.assertEqual(first_action.status_code, 200)
        self.assertEqual(first_action.data["workflow"]["current_stage_number"], 2)
        self.assertEqual(first_action.data["active_assignments"][0]["reviewer_id"], str(self.reviewer_2.id))

        second_assignment = first_action.data["active_assignments"][0]["id"]
        second_action = self.client.post(
            reverse("review-action", args=[document_id]),
            {"assignment_id": second_assignment, "action": "approve", "comment": "Approved."},
            format="json",
            **self.auth(self.reviewer_2),
        )

        self.assertEqual(second_action.status_code, 200)
        self.assertEqual(second_action.data["document"]["status"], DocumentStatus.APPROVED)
        self.assertEqual(second_action.data["workflow"]["status"], "approved")

    def test_timeline_returns_audit_events(self):
        template = self.create_template()
        submit_response = self.submit_document(template)
        document_id = submit_response.data["document"]["id"]

        response = self.client.get(reverse("document-timeline", args=[document_id]), **self.auth(self.submitter))

        self.assertEqual(response.status_code, 200)
        event_types = [event["event_type"] for event in response.data["timeline"]]
        self.assertIn("document.submitted", event_types)
        self.assertIn("workflow.started", event_types)
        self.assertIn("review.assignment_activated", event_types)

    def test_parallel_review_waits_for_all_active_reviewers(self):
        template = self.create_template(ApprovalMode.PARALLEL)
        submit_response = self.submit_document(template)
        document_id = submit_response.data["document"]["id"]
        assignments = submit_response.data["active_assignments"]

        self.assertEqual(len(assignments), 2)
        first_assignment = next(item for item in assignments if item["reviewer_id"] == str(self.reviewer_1.id))
        second_assignment = next(item for item in assignments if item["reviewer_id"] == str(self.reviewer_2.id))

        first_action = self.client.post(
            reverse("review-action", args=[document_id]),
            {"assignment_id": first_assignment["id"], "action": "approve"},
            format="json",
            **self.auth(self.reviewer_1),
        )

        self.assertEqual(first_action.status_code, 200)
        self.assertEqual(first_action.data["document"]["status"], DocumentStatus.IN_REVIEW)
        self.assertEqual(first_action.data["remaining_required_approvals"], 1)

        second_action = self.client.post(
            reverse("review-action", args=[document_id]),
            {"assignment_id": second_assignment["id"], "action": "approve"},
            format="json",
            **self.auth(self.reviewer_2),
        )

        self.assertEqual(second_action.status_code, 200)
        self.assertEqual(second_action.data["document"]["status"], DocumentStatus.APPROVED)

    def test_non_assigned_reviewer_cannot_act(self):
        template = self.create_template()
        submit_response = self.submit_document(template)
        document_id = submit_response.data["document"]["id"]
        first_assignment = submit_response.data["active_assignments"][0]["id"]

        response = self.client.post(
            reverse("review-action", args=[document_id]),
            {"assignment_id": first_assignment, "action": "approve"},
            format="json",
            **self.auth(self.reviewer_2),
        )

        self.assertEqual(response.status_code, 403)
