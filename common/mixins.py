from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse

class PaginatedListMixin(LoginRequiredMixin, ListView):
    paginate_by = 20

class LogListView(PaginatedListMixin):
    model = None
    template_name = "common/log_list.html"

    def get_queryset(self):
        return self.model.objects.all().order_by("-created_at")

class ToggleStatusView(LoginRequiredMixin, View):
    model = None
    field = None

    def post(self, request, *args, **kwargs):
        obj = get_object_or_404(self.model, pk=kwargs["pk"])
        setattr(obj, self.field, not getattr(obj, self.field))
        obj.save()
        return JsonResponse({"status": "ok", "id": obj.id})

class SenderScopedDeleteView(LoginRequiredMixin, DeleteView):
    def get_queryset(self):
        return super().get_queryset().filter(notification_sender=self.request.user)

class SenderScopedUpdateView(LoginRequiredMixin, UpdateView):
    def get_queryset(self):
        return super().get_queryset().filter(notification_sender=self.request.user)
