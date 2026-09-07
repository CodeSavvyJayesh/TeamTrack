"""
Files.

The download view is the security boundary. MEDIA_URL is not served by the web
server in production, so the ONLY way to read an uploaded file is through
FileDownloadView, which checks permission first and always sends the bytes as
an attachment with nosniff - an uploaded .html can never execute in this
origin.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView

from core.mixins import PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity

from .forms import FileFilterForm, UploadedFileForm
from .models import UploadedFile


class FileListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "storage/file_list.html"
    context_object_name = "files"
    paginate_by = 25
    page_title = "Files"

    def get_queryset(self):
        user = self.request.user
        queryset = UploadedFile.objects.visible_to(user).select_related(
            "uploaded_by", "related_task", "project"
        )
        self.filter_form = FileFilterForm(
            self.request.GET or None, show_member_filter=user.is_admin_user
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                queryset = queryset.filter(
                    Q(original_name__icontains=data["q"]) | Q(description__icontains=data["q"])
                )
            if data.get("member"):
                queryset = queryset.filter(uploaded_by=data["member"])
            if data.get("extension"):
                queryset = queryset.filter(
                    original_name__iendswith="." + data["extension"].lower().lstrip(".")
                )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class FileUploadView(LoginRequiredMixin, PageTitleMixin, CreateView):
    """Both administrators and members upload through this one view."""

    template_name = "storage/file_form.html"
    form_class = UploadedFileForm
    success_url = reverse_lazy("storage:list")
    page_title = "Upload a file"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.FILE_UPLOADED,
            target=self.object,
            subject=self.request.user,
            target_repr=f"Uploaded {self.object.original_name} ({self.object.size_display})",
        )
        messages.success(self.request, f"{self.object.original_name} uploaded.")
        return response


class FileDownloadView(LoginRequiredMixin, View):
    """
    Serves the bytes only after checking permission.

    In production, swap the FileResponse for an X-Accel-Redirect header so
    nginx sends the file - the permission check stays exactly where it is.
    """

    def get(self, request, pk):
        uploaded = get_object_or_404(UploadedFile, pk=pk)

        if not uploaded.may_be_read_by(request.user):
            # 404 rather than 403: a 403 would confirm the file exists.
            raise Http404("No such file.")

        try:
            handle = uploaded.file.open("rb")
        except (FileNotFoundError, ValueError):
            raise Http404("This file is missing from storage.")

        response = FileResponse(handle, as_attachment=True, filename=uploaded.original_name)
        response["X-Content-Type-Options"] = "nosniff"
        return response


class FileDeleteView(LoginRequiredMixin, PageTitleMixin, DeleteView):
    model = UploadedFile
    template_name = "storage/file_confirm_delete.html"
    success_url = reverse_lazy("storage:list")
    page_title = "Delete file"
    context_object_name = "file"

    def get_object(self, queryset=None):
        uploaded = get_object_or_404(UploadedFile, pk=self.kwargs["pk"])
        if not uploaded.may_be_deleted_by(self.request.user):
            raise PermissionDenied("You can only delete files you uploaded.")
        return uploaded

    def form_valid(self, form):
        uploaded = self.get_object()
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.FILE_DELETED,
            subject=uploaded.uploaded_by,
            target_repr=f"Deleted {uploaded.original_name}",
        )
        messages.success(self.request, f"{uploaded.original_name} deleted.")
        return super().form_valid(form)
