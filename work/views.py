"""
Tasks and projects.

Note the pattern in TaskListView / TaskDetailView: the queryset is narrowed by
`Task.objects.for_user(request.user)`, so a member requesting another member's
task gets a 404. The template never has to hide anything for safety.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity
from integrations.ether.config import notify_ether
from storage.models import UploadedFile

from .forms import ProjectForm, TaskFilterForm, TaskForm, TaskStatusForm
from .models import Project, Task


class TaskListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "work/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_page_title(self):
        return "All tasks" if self.request.user.is_admin_user else "My tasks"

    def get_queryset(self):
        user = self.request.user
        queryset = (
            Task.objects.for_user(user)
            .select_related("assigned_to", "project")
        )
        self.filter_form = TaskFilterForm(
            self.request.GET or None, show_member_filter=user.is_admin_user
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                queryset = queryset.filter(
                    Q(title__icontains=data["q"]) | Q(description__icontains=data["q"])
                )
            if data.get("member"):
                queryset = queryset.filter(assigned_to=data["member"])
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
            if data.get("priority"):
                queryset = queryset.filter(priority=data["priority"])
            if data.get("due_before"):
                queryset = queryset.filter(due_date__lte=data["due_before"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.get_page_title()
        context["filter_form"] = self.filter_form
        visible = Task.objects.for_user(self.request.user)
        context["counts"] = {
            "total": visible.count(),
            "open": visible.open().count(),
            "completed": visible.completed().count(),
            "overdue": visible.overdue().count(),
        }
        return context


class TaskDetailView(LoginRequiredMixin, PageTitleMixin, DetailView):
    template_name = "work/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return Task.objects.for_user(self.request.user).select_related(
            "assigned_to", "project", "created_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.title
        # A member may change status on their own task, and nothing else.
        context["status_form"] = TaskStatusForm(instance=self.object)
        context["can_edit_fully"] = self.request.user.is_admin_user
        # Attachments go through the same visibility rule as the Files page.
        # Listing self.object.files.all() would show a member the name and size
        # of an ADMIN_ONLY file attached to their own task. The download would
        # still be refused, but a filename alone can leak plenty.
        context["files"] = UploadedFile.objects.visible_to(self.request.user).filter(
            related_task=self.object
        )
        return context


class TaskCreateView(AdminRequiredMixin, PageTitleMixin, CreateView):
    template_name = "work/task_form.html"
    form_class = TaskForm
    page_title = "New task"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.TASK_CREATED,
            target=self.object,
            subject=self.object.assigned_to,
            target_repr=f"Created '{self.object.title}' for {self.object.assigned_to.full_name}",
        )
        notify_ether("task.created", {"task_id": self.object.pk,
                                      "member_id": self.object.assigned_to_id})
        messages.success(self.request, "Task created.")
        return response


class TaskUpdateView(AdminRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "work/task_form.html"
    form_class = TaskForm
    model = Task
    page_title = "Edit task"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.TASK_UPDATED,
            target=self.object,
            subject=self.object.assigned_to,
            target_repr=f"Edited '{self.object.title}'",
        )
        messages.success(self.request, "Task updated.")
        return response


class TaskStatusUpdateView(LoginRequiredMixin, UpdateView):
    """
    The one write a member is allowed to make to a task.

    get_queryset() restricts it to their own tasks, and the form exposes only
    `status`, so this endpoint cannot be used to change anything else.
    """

    form_class = TaskStatusForm
    http_method_names = ["post"]

    def get_queryset(self):
        return Task.objects.for_user(self.request.user)

    def form_valid(self, form):
        previous = Task.objects.get(pk=self.object.pk).status
        response = super().form_valid(form)

        if previous != self.object.status:
            log_activity(
                actor=self.request.user,
                verb=ActivityLog.Verb.TASK_STATUS_CHANGED,
                target=self.object,
                subject=self.object.assigned_to,
                target_repr=(
                    f"'{self.object.title}': {previous.replace('_', ' ').title()} "
                    f"to {self.object.get_status_display()}"
                ),
            )
            if self.object.status == Task.Status.COMPLETED:
                notify_ether("task.completed", {"task_id": self.object.pk,
                                                "member_id": self.object.assigned_to_id})
        messages.success(self.request, f"Status set to {self.object.get_status_display()}.")
        return response

    def form_invalid(self, form):
        messages.error(self.request, "That is not a valid status.")
        return redirect("work:task_detail", pk=self.object.pk)

    def get_success_url(self):
        return reverse_lazy("work:task_detail", args=[self.object.pk])


class ProjectListView(AdminRequiredMixin, PageTitleMixin, ListView):
    template_name = "work/project_list.html"
    context_object_name = "projects"
    model = Project
    page_title = "Projects"


class ProjectCreateView(AdminRequiredMixin, PageTitleMixin, CreateView):
    template_name = "work/project_form.html"
    form_class = ProjectForm
    success_url = reverse_lazy("work:project_list")
    page_title = "New project"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Project created.")
        return super().form_valid(form)


class ProjectUpdateView(AdminRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "work/project_form.html"
    form_class = ProjectForm
    model = Project
    success_url = reverse_lazy("work:project_list")
    page_title = "Edit project"
