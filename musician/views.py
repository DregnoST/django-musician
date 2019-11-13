
from django.core.exceptions import ImproperlyConfigured
from itertools import groupby
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.http import is_safe_url
from django.views.generic.base import RedirectView, TemplateView
from django.views.generic.edit import FormView
from django.views.generic.list import ListView

from . import api, get_version
from .auth import login as auth_login
from .auth import logout as auth_logout
from .forms import LoginForm
from .mixins import CustomContextMixin, ExtendedPaginationMixin, UserTokenRequiredMixin
from .models import MailService


class DashboardView(CustomContextMixin, UserTokenRequiredMixin, TemplateView):
    template_name = "musician/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # TODO retrieve all data needed from orchestra
        raw_domains = self.orchestra.retrieve_service_list('domain')

        context.update({
            'domains': raw_domains
        })

        return context


class ServiceListView(CustomContextMixin, ExtendedPaginationMixin, UserTokenRequiredMixin, ListView):
    """Base list view to all services"""
    service = None
    template_name = "musician/service_list.html"  # TODO move to ServiceListView

    def get_queryset(self):
        if self.service_class is None or self.service_class.name is None:
            raise ImproperlyConfigured(
                "ServiceListView requires a definiton of 'service'")

        return self.orchestra.retrieve_service_list(self.service_class.name)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'service': self.service_class,
        })
        return context


class MailView(ServiceListView):
    service_class = MailService

    def get_queryset(self):
        def retrieve_mailbox(value):
            mailboxes = value.get('mailboxes')

            if len(mailboxes) == 0:
                return ''

            return mailboxes[0]['id']

        # group addresses with the same mailbox
        raw_data = self.orchestra.retrieve_service_list(
            self.service_class.name)
        addresses = []
        for key, group in groupby(raw_data, retrieve_mailbox):
            aliases = []
            data = {}
            for thing in group:
                aliases.append(thing.pop('name'))
                data = thing

            data['names'] = aliases
            addresses.append(MailService(data))

        return addresses


class MailingListsView(ServiceListView):
    template_name = "musician/mailinglists.html"

    def get_queryset(self):
        return self.orchestra.retrieve_service_list('mailinglist')


class DatabasesView(CustomContextMixin, UserTokenRequiredMixin, TemplateView):
    template_name = "musician/databases.html"


class SaasView(CustomContextMixin, UserTokenRequiredMixin, TemplateView):
    template_name = "musician/saas.html"


class LoginView(FormView):
    template_name = 'auth/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('musician:dashboard')
    redirect_field_name = 'next'
    extra_context = {'version': get_version()}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        """Security check complete. Log the user in."""
        auth_login(self.request, form.username, form.token)
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or self.success_url

    def get_redirect_url(self):
        """Return the user-originating redirect URL if it's safe."""
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name, '')
        )
        url_is_safe = is_safe_url(
            url=redirect_to,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        )
        return redirect_to if url_is_safe else ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            self.redirect_field_name: self.get_redirect_url(),
            **(self.extra_context or {})
        })
        return context


class LogoutView(RedirectView):
    """
    Log out the user.
    """
    permanent = False
    pattern_name = 'musician:login'

    def get_redirect_url(self, *args, **kwargs):
        """
        Logs out the user.
        """
        auth_logout(self.request)
        return super().get_redirect_url(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Logout may be done via POST."""
        return self.get(request, *args, **kwargs)
