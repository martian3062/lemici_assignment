from django.urls import path

from .views import ReviewActionView, SubmitDocumentView, TimelineView


urlpatterns = [
    path("documents", SubmitDocumentView.as_view(), name="submit-document"),
    path("documents/<uuid:document_id>/review-actions", ReviewActionView.as_view(), name="review-action"),
    path("documents/<uuid:document_id>/timeline", TimelineView.as_view(), name="document-timeline"),
]
