from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse, HttpResponseForbidden

from django.db.models import Sum, Q, F

from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.core.exceptions import ValidationError
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils import timezone
from django.template.response import TemplateResponse
from django.forms import inlineformset_factory, BaseInlineFormSet
from decimal import Decimal
from django.utils.safestring import mark_safe
from datetime import datetime, time, timedelta
from admin_auto_filters.filters import AutocompleteFilter

# Register custom template filters
import rental.templatetags.custom_filters

from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Client, Battery, Rental, RentalBatteryAssignment,
    Payment, ExpenseCategory, Expense, Repair, BatteryStatusLog,
    FinancePartner, OwnerContribution, OwnerWithdrawal, MoneyTransfer, FinanceAdjustment
)


@admin.register(FinancePartner)
class FinancePartnerAdmin(SimpleHistoryAdmin):
    list_display = ("id", "user", "role", "share_percent", "active")
    list_filter = ("role", "active")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(OwnerContribution)
class OwnerContributionAdmin(SimpleHistoryAdmin):
    list_display = ("id", "partner", "amount", "date", "source")
    list_filter = ("source", "date")
    autocomplete_fields = ("partner", "expense")
    search_fields = ("note", "partner__user__username")


@admin.register(OwnerWithdrawal)
class OwnerWithdrawalAdmin(SimpleHistoryAdmin):
    list_display = ("id", "partner", "amount", "date")
    list_filter = ("date",)
    autocomplete_fields = ("partner",)
    search_fields = ("note", "partner__user__username")


@admin.register(MoneyTransfer)
class MoneyTransferAdmin(SimpleHistoryAdmin):
    list_display = ("id", "from_partner", "to_partner", "amount", "date", "purpose", "use_collected")
    list_filter = ("purpose", "use_collected", "date")
    autocomplete_fields = ("from_partner", "to_partner")
    search_fields = ("note", "from_partner__user__username", "to_partner__user__username")

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        qp = request.GET
        if "from_partner" in qp:
            data["from_partner"] = qp.get("from_partner")
        if "to_partner" in qp:
            data["to_partner"] = qp.get("to_partner")
        if "amount" in qp:
            try:
                data["amount"] = qp.get("amount")
            except Exception:
                pass
        if "purpose" in qp:
            data["purpose"] = qp.get("purpose")
        if "use_collected" in qp:
            val = qp.get("use_collected")
            data["use_collected"] = val in ("1", "true", "True", "on")
        if "date" in qp:
            data["date"] = qp.get("date")
        return data


@admin.register(FinanceAdjustment)
class FinanceAdjustmentAdmin(SimpleHistoryAdmin):
    list_display = ("id", "target", "amount", "date")
    list_filter = ("target", "date")
    search_fields = ("note",)


# Lightweight finance overview entry under Admin Index


class FinanceTransferForm(forms.Form):
    from_partner = forms.IntegerField()
    to_partner = forms.IntegerField()
    amount = forms.DecimalField(max_digits=12, decimal_places=2)
    date = forms.DateField(required=False)
    purpose = forms.ChoiceField(choices=MoneyTransfer.Purpose.choices)
    use_collected = forms.BooleanField(required=False)
    note = forms.CharField(required=False)

class FinanceWithdrawalForm(forms.Form):
    partner = forms.IntegerField()
    amount = forms.DecimalField(max_digits=12, decimal_places=2)
    date = forms.DateField(required=False)
    note = forms.CharField(required=False)


class FinanceOverviewAdmin(admin.ModelAdmin):
    change_list_template = "admin/finance_overview.html"
    CUTOFF_DATE = timezone.datetime(2025, 9, 1).date()

    def _compute_period(self, request):
        today = timezone.localdate()
        preset = request.GET.get("preset") or "month"
        start_param = request.GET.get("start")
        end_param = request.GET.get("end")
        if preset == "prev":
            first_of_this = today.replace(day=1)
            end = first_of_this - timezone.timedelta(days=1)
            start = end.replace(day=1)
        elif preset == "ytd":
            start = today.replace(month=1, day=1)
            end = today
        elif preset == "custom":
            from datetime import datetime as _dt
            def parse_d(s):
                try:
                    return _dt.fromisoformat(s).date()
                except Exception:
                    return None
            start = parse_d(start_param) or today.replace(day=1)
            end = parse_d(end_param) or today
        else:
            start = today.replace(day=1)
            end = today
        if start < self.CUTOFF_DATE:
            start = self.CUTOFF_DATE
        return start, end

    def has_module_permission(self, request):
        # только владельцы видят раздел
        return FinancePartner.objects.filter(user=request.user, role=FinancePartner.Role.OWNER, active=True).exists()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("create-transfer/", self.admin_site.admin_view(self.create_transfer_view), name="finance_create_transfer"),
            path("create-withdrawal/", self.admin_site.admin_view(self.create_withdrawal_view), name="finance_create_withdrawal"),
        ]
        return custom + urls

    def _redirect_back(self, request):
        ret = request.POST.get("return_url") or request.META.get("HTTP_REFERER")
        if not ret:
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        return HttpResponseRedirect(ret)

    def _ensure_owner(self, request):
        if not FinancePartner.objects.filter(user=request.user, role=FinancePartner.Role.OWNER, active=True).exists():
            return False
        return True

    def create_transfer_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if not self._ensure_owner(request):
            if is_ajax:
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            return HttpResponseForbidden()
        try:
            from_id = int(request.POST.get("from_partner") or 0)
            to_id = int(request.POST.get("to_partner") or 0)
            amount = Decimal(request.POST.get("amount") or "0")
            purpose = request.POST.get("purpose") or MoneyTransfer.Purpose.OTHER
            use_collected = (request.POST.get("use_collected") in ("1", "true", "True", "on"))
            date_str = request.POST.get("date")
            date_val = timezone.localdate()
            if date_str:
                try:
                    date_val = timezone.datetime.fromisoformat(date_str).date()
                except Exception:
                    pass
            if from_id <= 0 or to_id <= 0 or amount <= 0:
                raise ValidationError("Некорректные данные перевода")
            MoneyTransfer.objects.create(
                from_partner_id=from_id,
                to_partner_id=to_id,
                amount=amount,
                date=date_val,
                purpose=purpose,
                use_collected=use_collected,
            )
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Перевод создан")
        except Exception as e:
            if is_ajax:
                return JsonResponse({"ok": False, "error": str(e)[:300]})
            messages.error(request, f"Ошибка: {e}")
        return self._redirect_back(request)

    def create_withdrawal_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if not self._ensure_owner(request):
            if is_ajax:
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            return HttpResponseForbidden()
        try:
            partner_id = int(request.POST.get("partner") or 0)
            amount = Decimal(request.POST.get("amount") or "0")
            note = request.POST.get("note") or ""
            date_str = request.POST.get("date")
            date_val = timezone.localdate()
            if date_str:
                try:
                    date_val = timezone.datetime.fromisoformat(date_str).date()
                except Exception:
                    pass
            if partner_id <= 0 or amount <= 0:
                raise ValidationError("Некорректные данные выплаты")
            fp = FinancePartner.objects.get(pk=partner_id)
            if fp.role != FinancePartner.Role.OWNER:
                raise ValidationError("Выплаты доступны только владельцам")
            OwnerWithdrawal.objects.create(partner_id=partner_id, amount=amount, date=date_val, note=note)
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Выплата создана")
        except Exception as e:
            if is_ajax:
                return JsonResponse({"ok": False, "error": str(e)[:300]})
            messages.error(request, f"Ошибка: {e}")
        return self._redirect_back(request)

        # только владельцы видят раздел
        return FinancePartner.objects.filter(user=request.user, role=FinancePartner.Role.OWNER, active=True).exists()

    def changelist_view(self, request, extra_context=None):
        start_d, end_d = self._compute_period(request)
        partners = FinancePartner.objects.filter(active=True).values("id", "user_id", "role", "share_percent")
        user_to_partner = {p["user_id"]: p["id"] for p in partners}
        partner_roles = {p["id"]: p["role"] for p in partners}
        partner_shares = {p["id"]: (p["share_percent"] or 0) for p in partners}

        # Income for period
        income_qs = (
            Payment.objects
            .filter(date__gte=start_d, date__lte=end_d, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD], created_by_id__in=list(user_to_partner.keys()))
            .values("created_by_id")
            .annotate(total=Sum("amount"))
        )
        income_by_user = {row["created_by_id"]: row["total"] or 0 for row in income_qs}
        income_total = sum(income_by_user.values())

        # Transfers affecting collected (period)
        mt_in = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, use_collected=True)
            .values("to_partner_id")
            .annotate(total=Sum("amount"))
        )
        mt_out = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, use_collected=True)
            .values("from_partner_id")
            .annotate(total=Sum("amount"))
        )
        incoming_by_partner = {row["to_partner_id"]: row["total"] or 0 for row in mt_in}
        outgoing_by_partner = {row["from_partner_id"]: row["total"] or 0 for row in mt_out}

        # Period delta for collected
        collected_delta_by_partner = {}
        for user_id, partner_id in user_to_partner.items():
            inc = income_by_user.get(user_id, 0)
            inc_in = incoming_by_partner.get(partner_id, 0)
            out = outgoing_by_partner.get(partner_id, 0)
            collected_delta_by_partner[partner_id] = inc + inc_in - out
        collected_delta_total = sum(collected_delta_by_partner.values())

        # Contributions/withdrawals for period (invested delta)
        contr_qs = (
            OwnerContribution.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("partner_id")
            .annotate(total=Sum("amount"))
        )
        withdr_qs = (
            OwnerWithdrawal.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("partner_id")
            .annotate(total=Sum("amount"))
        )
        contr_by_partner = {row["partner_id"]: row["total"] or 0 for row in contr_qs}
        withdr_by_partner = {row["partner_id"]: row["total"] or 0 for row in withdr_qs}

        from .models import FinanceAdjustment as FA
        adj_rows = (
            FA.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("target")
            .annotate(total=Sum("amount"))
        )
        adj_map = {row["target"]: row["total"] or 0 for row in adj_rows}
        adj_invested = adj_map.get(FA.Target.INVESTED, 0)
        adj_collected = adj_map.get(FA.Target.COLLECTED, 0)
        adj_settlement = adj_map.get(FA.Target.OWNER_SETTLEMENT, 0)

        invested_delta_by_owner = {}
        for pid, role in partner_roles.items():
            if role != FinancePartner.Role.OWNER:
                continue
            invested_delta_by_owner[pid] = (contr_by_partner.get(pid, 0) - withdr_by_partner.get(pid, 0))
        invested_delta_total = sum(invested_delta_by_owner.values()) + adj_invested

        # Opening balances (up to day before start)
        from datetime import timedelta
        opening_available = start_d > self.CUTOFF_DATE
        collected_open_by_partner = {}
        invested_open_by_owner = {}
        if opening_available:
            open_end = start_d - timedelta(days=1)
            inc_open_qs = (
                Payment.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD], created_by_id__in=list(user_to_partner.keys()))
                .values("created_by_id")
                .annotate(total=Sum("amount"))
            )
            mt_in_open = (
                MoneyTransfer.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, use_collected=True)
                .values("to_partner_id")
                .annotate(total=Sum("amount"))
            )
            mt_out_open = (
                MoneyTransfer.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, use_collected=True)
                .values("from_partner_id")
                .annotate(total=Sum("amount"))
            )
            inc_open_by_user = {row["created_by_id"]: row["total"] or 0 for row in inc_open_qs}
            in_open_by_partner = {row["to_partner_id"]: row["total"] or 0 for row in mt_in_open}
            out_open_by_partner = {row["from_partner_id"]: row["total"] or 0 for row in mt_out_open}

            adj_open_rows = (
                FA.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("target")
                .annotate(total=Sum("amount"))
            )
            adj_open_map = {row["target"]: row["total"] or 0 for row in adj_open_rows}
            adj_open_collected = adj_open_map.get(FA.Target.COLLECTED, 0)

            for user_id, partner_id in user_to_partner.items():
                inc = inc_open_by_user.get(user_id, 0)
                inc_in = in_open_by_partner.get(partner_id, 0)
                out = out_open_by_partner.get(partner_id, 0)
                collected_open_by_partner[partner_id] = inc + inc_in - out
            # Apply adjustment (global) to total collected open
            collected_open_total = sum(collected_open_by_partner.values()) + adj_open_collected

            contr_open_qs = (
                OwnerContribution.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("partner_id")
                .annotate(total=Sum("amount"))
            )
            withdr_open_qs = (
                OwnerWithdrawal.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("partner_id")
                .annotate(total=Sum("amount"))
            )
            contr_open_by_partner = {row["partner_id"]: row["total"] or 0 for row in contr_open_qs}
            withdr_open_by_partner = {row["partner_id"]: row["total"] or 0 for row in withdr_open_qs}
            adj_open_invested = adj_open_map.get(FA.Target.INVESTED, 0)
            for pid, role in partner_roles.items():
                if role != FinancePartner.Role.OWNER:
                    continue
                invested_open_by_owner[pid] = contr_open_by_partner.get(pid, 0) - withdr_open_by_partner.get(pid, 0)
            invested_open_total = sum(invested_open_by_owner.values()) + adj_open_invested
        else:
            collected_open_total = 0
            invested_open_total = 0

        # Closing balances
        collected_total = collected_open_total + collected_delta_total + adj_collected
        invested_total = invested_open_total + invested_delta_total

        # Per-user display prep
        from django.contrib.auth import get_user_model
        users = get_user_model().objects.filter(id__in=list(user_to_partner.keys())).values("id", "username")
        uid_to_username = {u["id"]: u["username"] for u in users}
        pid_to_username = {pid: uid_to_username.get(uid, str(pid)) for uid, pid in user_to_partner.items()}

        income_rows = [
            {"created_by__username": uid_to_username.get(uid, str(uid)), "total": total}
            for uid, total in sorted(income_by_user.items(), key=lambda kv: uid_to_username.get(kv[0], str(kv[0])))
        ]
        collected_rows = [
            {"partner_id": pid, "username": pid_to_username.get(pid, str(pid)), "delta": collected_delta_by_partner.get(pid, 0), "open": collected_open_by_partner.get(pid, 0) if opening_available else 0}
            for pid in sorted(user_to_partner.values(), key=lambda x: pid_to_username.get(x, str(x)))
        ]
        for row in collected_rows:
            row["close"] = row["open"] + row["delta"]
        invested_rows = [
            {"partner_id": pid, "username": pid_to_username.get(pid, str(pid)), "delta": invested_delta_by_owner.get(pid, 0), "open": invested_open_by_owner.get(pid, 0) if opening_available else 0}
            for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER
        ]
        for row in invested_rows:
            row["close"] = row["open"] + row["delta"]

        # Owner settlements (owner_to_owner, use_collected=False) for the period
        settlements_qs = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER, use_collected=False)
            .values("from_partner_id", "to_partner_id")
            .annotate(total=Sum("amount"))
        )
        settlements_rows = []
        settlements_total = 0
        for r in settlements_qs:
            from_name = pid_to_username.get(r["from_partner_id"], str(r["from_partner_id"]))
            to_name = pid_to_username.get(r["to_partner_id"], str(r["to_partner_id"]))
            total = r["total"] or 0
            settlements_total += total
            settlements_rows.append({"from": from_name, "to": to_name, "total": total})

        if extra_context is None:
            extra_context = {}
        extra_context.update({
            "start": start_d,
            "end": end_d,
            "income_rows": income_rows,
            "income_total": income_total,
            "collected_rows": collected_rows,
            "collected_open_total": collected_open_total,
            "collected_delta_total": collected_delta_total,
            "collected_total": collected_total,
            "invested_rows": invested_rows,
            "invested_open_total": invested_open_total,
            "invested_delta_total": invested_delta_total,
            "invested_total": invested_total,
            "settlements_rows": settlements_rows,
            "settlements_total": settlements_total,
            "settlements_adj_total": adj_settlement,
            "opening_available": opening_available,
        })

        # Last 5 withdrawals for footer
        last_withdrawals_qs = (
            OwnerWithdrawal.objects
            .order_by('-date', '-id')
            .select_related('partner__user')[:5]
        )
        last_withdrawals = [
            {
                'date': w.date,
                'partner': getattr(w.partner.user, 'username', str(w.partner_id)),
                'amount': w.amount,
            } for w in last_withdrawals_qs
        ]
        extra_context.update({
            'last_withdrawals': last_withdrawals,
        })

        # Suggested owner-to-owner transfers based on collected vs share (period-only)
        owners = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        # Actual collected for owners in period (delta)
        collected_owner_delta = {pid: collected_delta_by_partner.get(pid, 0) for pid in owners}
        # Desired per-share from total income (period)
        total_income_period = income_total
        total_share = sum([float(partner_shares.get(pid, 0)) for pid in owners]) or 100.0
        share_norm = {pid: float(partner_shares.get(pid, 0))/total_share for pid in owners}
        desired_collected = {pid: Decimal(total_income_period) * Decimal(share_norm.get(pid, 0)) for pid in owners}
        diff_collected = {pid: Decimal(collected_owner_delta.get(pid, 0)) - desired_collected.get(pid, Decimal(0)) for pid in owners}
        over_c = [(pid, v) for pid, v in diff_collected.items() if v > 0]
        under_c = [(pid, -v) for pid, v in diff_collected.items() if v < 0]
        over_c.sort(key=lambda x: x[1], reverse=True)
        under_c.sort(key=lambda x: x[1], reverse=True)
        settlements_by_collected = []
        i = j = 0
        while i < len(over_c) and j < len(under_c):
            pid_over, amt_over = over_c[i]
            pid_under, amt_under = under_c[j]
            tr = min(amt_over, amt_under)
            if tr > 0:
                settlements_by_collected.append({
                    "from": pid_over,
                    "to": pid_under,
                    "total": tr
                })
            over_c[i] = (pid_over, amt_over - tr)
            under_c[j] = (pid_under, amt_under - tr)
            if over_c[i][1] == 0:
                i += 1
            if under_c[j][1] == 0:
                j += 1
        # Two-owners highlight
        highlight_reco = None
        if len(owners) == 2:
            a, b = owners[0], owners[1]
            a_name = pid_to_username.get(a, str(a))
            b_name = pid_to_username.get(b, str(b))
            # T = (C_a - C_b)/2
            T = (Decimal(collected_owner_delta.get(a, 0)) - Decimal(collected_owner_delta.get(b, 0))) / Decimal(2)
            if T > 0:
                highlight_reco = {"from": a_name, "to": b_name, "total": T}
            elif T < 0:
                highlight_reco = {"from": b_name, "to": a_name, "total": -T}
        extra_context.update({
            "collected_settlements": [
                {"from": pid_to_username.get(r["from"], str(r["from"])), "to": pid_to_username.get(r["to"], str(r["to"])), "total": r["total"], "from_id": r["from"], "to_id": r["to"]}
                for r in settlements_by_collected
            ],
            "collected_settlements_highlight": highlight_reco,
            "collected_owner_delta": {pid_to_username.get(pid, str(pid)): collected_owner_delta.get(pid, 0) for pid in owners},
            "desired_collected": {pid_to_username.get(pid, str(pid)): desired_collected.get(pid, 0) for pid in owners},
        })

        # Moderators' debts to owners for period: income by moderator minus out transfers use_collected
        moderators = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.MODERATOR]
        income_by_partner = {}
        for uid, pid in user_to_partner.items():
            if pid in moderators:
                income_by_partner[pid] = income_by_user.get(uid, 0)
        # Last 5 transfers for two categories for footer blocks (show after tables)
        last_mod_qs = (
            MoneyTransfer.objects.filter(purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER)
            .order_by('-date', '-id')
            .select_related('from_partner__user', 'to_partner__user')[:5]
        )
        last_owner_qs = (
            MoneyTransfer.objects.filter(purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER)
            .order_by('-date', '-id')
            .select_related('from_partner__user', 'to_partner__user')[:5]
        )
        # Outgoing transfers from moderators within period (for debt calc)
        mt_out_by_mod = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, use_collected=True, from_partner_id__in=moderators)
            .values("from_partner_id")
            .annotate(total=Sum("amount"))
        )
        def tr_row(tr):
            return {
                'date': tr.date,
                'from': getattr(tr.from_partner.user, 'username', str(tr.from_partner_id)),
                'to': getattr(tr.to_partner.user, 'username', str(tr.to_partner_id)),
                'amount': tr.amount,
            }
        extra_context.update({
            'last_mod_to_owner': [tr_row(t) for t in last_mod_qs],
            'last_owner_to_owner': [tr_row(t) for t in last_owner_qs],
        })
        mt_out_by_mod_map = {row["from_partner_id"]: row["total"] or 0 for row in mt_out_by_mod}
        moderator_debts = []
        for pid in moderators:
            owed = Decimal(income_by_partner.get(pid, 0)) - Decimal(mt_out_by_mod_map.get(pid, 0))
            if owed > 0:
                moderator_debts.append({
                    "partner_id": pid,
                    "username": pid_to_username.get(pid, str(pid)),
                    "amount": owed,
                })
        extra_context.update({"moderator_debts": moderator_debts})

        # Profit share block (split by owner shares)
        # Income I
        I = sum(income_by_user.values())
        
        # Company expenses E: only paid from collected funds
        E = Expense.objects.filter(date__gte=start_d, date__lte=end_d, paid_source=Expense.PaidSource.COLLECTED).aggregate(s=Sum("amount"))['s'] or 0
        
        # Adjustments to profit if needed (reuse collected/invested logic as neutral here)
        P = I - E  # base profit without extra adj
        
        # Owners and their shares (normalize to 1.0)
        owners = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        total_share = sum([float(partner_shares.get(pid, 0)) for pid in owners]) or 100.0
        share_norm = {pid: float(partner_shares.get(pid, 0))/total_share for pid in owners}
        
        # Due to each owner from profit
        D_by_owner = {pid: P * Decimal(share_norm.get(pid, 0)) for pid in owners}
        D_total = sum(D_by_owner.values())
        
        # Actually withdrawn by owners in period
        W_by_owner = {row["partner_id"]: row["total"] or 0 for row in (
            OwnerWithdrawal.objects.filter(date__gte=start_d, date__lte=end_d, partner_id__in=owners)
            .values("partner_id").annotate(total=Sum("amount"))
        )}
        W_total = sum(W_by_owner.values())
        
        # How issued funds should be split by shares
        R_by_owner = {pid: Decimal(W_total) * Decimal(share_norm.get(pid, 0)) for pid in owners}
        
        # Suggested owner-to-owner transfer to rebalance already issued funds
        # For two owners it's a single number; for N owners show list of imbalances
        imbalance = {pid: Decimal(W_by_owner.get(pid, 0)) - R_by_owner.get(pid, Decimal(0)) for pid in owners}
        # Positive -> owner received more than proportional, should pay out; Negative -> should receive
        over = [(pid, v) for pid, v in imbalance.items() if v > 0]
        under = [(pid, -v) for pid, v in imbalance.items() if v < 0]
        over.sort(key=lambda x: x[1], reverse=True)
        under.sort(key=lambda x: x[1], reverse=True)
        settlements_suggest = []
        i = j = 0
        while i < len(over) and j < len(under):
            pid_over, amt_over = over[i]
            pid_under, amt_under = under[j]
            tr = min(amt_over, amt_under)
            if tr > 0:
                settlements_suggest.append({
                    "from": pid_over,
                    "to": pid_under,
                    "total": tr
                })
            over[i] = (pid_over, amt_over - tr)
            under[j] = (pid_under, amt_under - tr)
            if over[i][1] == 0:
                i += 1
            if under[j][1] == 0:
                j += 1
        
        # Company owes to owners (not yet issued)
        C_total = Decimal(D_total) - Decimal(W_total)
        C_by_owner = {pid: D_by_owner.get(pid, 0) - Decimal(W_by_owner.get(pid, 0)) for pid in owners}
        
        # Prepare display structures
        profit_rows = []
        for pid in owners:
            profit_rows.append({
                "username": pid_to_username.get(pid, str(pid)),
                "share": round(Decimal(share_norm.get(pid, 0)) * Decimal(100), 2),
                "due": D_by_owner.get(pid, 0),
                "withdrawn": Decimal(W_by_owner.get(pid, 0)),
                "withdrawn_should": R_by_owner.get(pid, 0),
                "company_owes": C_by_owner.get(pid, 0),
            })
        settlements_suggest_rows = [
            {"from": pid_to_username.get(r["from"], str(r["from"])), "to": pid_to_username.get(r["to"], str(r["to"])), "total": r["total"]}
            for r in settlements_suggest
        ]
        extra_context.update({
            "profit_income": I,
            "profit_expenses": E,
            "profit_total": P,
            "profit_rows": profit_rows,
            "profit_company_owes_total": C_total,
            "profit_settlements_suggest": settlements_suggest_rows,
        })

        # Render with admin each_context so sidebar/menus are present, honoring GET params
        base_ctx = self.admin_site.each_context(request)
        context = {**base_ctx, **(extra_context or {}), "request": request, "opts": self.model._meta, "title": self.model._meta.verbose_name_plural}
        return TemplateResponse(request, self.change_list_template, context)

        return super().changelist_view(request, extra_context=extra_context)


# Register FinanceOverview using proxy model
from .models import FinanceOverviewProxy
try:
    @admin.register(FinanceOverviewProxy)
    class FinanceOverviewProxyAdmin(FinanceOverviewAdmin):
        pass
except admin.sites.AlreadyRegistered:
    pass

class ActiveRentalFilter(admin.SimpleListFilter):
    title = "Активный договор"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (
            ("1", "С активным"),
            ("0", "Без активного"),
        )

    def queryset(self, request, queryset):
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        queryset = queryset.annotate(has_active=Exists(active_qs))
        if self.value() == "1":
            return queryset.filter(has_active=True)
        if self.value() == "0":
            return queryset.filter(has_active=False)
        return queryset


@admin.register(Client)
class ClientAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "phone", "pesel", "created_at", "has_active")
    list_filter = (ActiveRentalFilter,)
    search_fields = ("name", "phone", "pesel")

    def has_active(self, obj):
        return getattr(obj, "has_active", False)
    has_active.boolean = True
    has_active.short_description = "Активный договор"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        client = self.get_object(request, object_id)
        if not client:
            return super().change_view(request, object_id, form_url, extra_context)

        # Получаем все root-группы договоров клиента
        root_rentals = client.rentals.filter(parent__isnull=True).order_by("contract_code")

        # Собираем данные для шаблона
        rental_data = []
        now = timezone.now()
        for root in root_rentals:
            versions = root.group_versions()
            start = versions.first().start_at if versions.exists() else None
            end = versions.last().end_at if versions.exists() else None
            days_total = (end or now) - (start or now)
            days_total = days_total.days if days_total else 0
            billable_days = sum(v.billable_days() for v in versions)
            charges = root.group_charges_until(now)
            paid = root.group_paid_total()
            balance = (paid or Decimal(0)) - (charges or Decimal(0))
            deposit = root.group_deposit_total()
            # Определяем цветовую метку баланса (зелёный, если не должен)
            if (charges or 0) == 0 and (paid or 0) == 0:
                color = 'gray'
            elif balance >= 0:
                color = 'green'
            elif deposit and (balance + deposit) >= 0:
                color = 'yellow'
            else:
                color = 'red'
            rental_data.append({
                "contract_code": root.contract_code,
                "version_range": f"v1–v{versions.count()}",
                "start": start,
                "end": end,
                "days_total": days_total,
                "billable_days": billable_days,
                "charges": charges,
                "paid": paid,
                "balance": balance,
                "deposit": deposit,
                "color": color,
                "url": reverse("admin:rental_rental_change", args=[root.pk]),
            })

        # Платежи по всем договорам клиента
        payments = Payment.objects.filter(rental__root__in=root_rentals).order_by("date")

        if extra_context is None:
            extra_context = {}
        extra_context["rental_data"] = rental_data
        extra_context["payments"] = payments

        return super().change_view(request, object_id, form_url, extra_context)

    list_filter = (ActiveRentalFilter,)

    class Media:
        js = [
            "https://unpkg.com/htmx.org@1.9.2",
            "https://unpkg.com/htmx.org@1.9.2/dist/ext/morphdom-swap.umd.js",
        ]

    def balance_badge(self, obj):
        # Суммарный баланс по всем root-догорам клиента: Оплатил - Должен
        roots = obj.rentals.filter(parent__isnull=True)
        from decimal import Decimal
        charges = Decimal(0)
        paid = Decimal(0)
        deposit = Decimal(0)
        now = timezone.now()
        for r in roots:
            charges += r.group_charges_until(now)
            paid += r.group_paid_total()
            deposit += r.group_deposit_total()
        balance = paid - charges
        color = "secondary"
        if charges == 0 and paid == 0:
            color = "secondary"
        elif balance >= 0:
            color = "success"
        elif (balance + deposit) >= 0:
            color = "warning"
        else:
            color = "danger"
        formatted = f"{balance:.2f}"
        return format_html('<span class="badge badge-balance bg-{}">{}</span>', color, formatted)
    balance_badge.short_description = "Баланс"

    def changelist_view(self, request, extra_context=None):
        self.list_filter = (ActiveRentalFilter,)
        if getattr(request, "htmx", False):
            # Для HTMX отдаём только таблицу результатов
            self.list_display = ("id", "name", "phone", "pesel", "created_at", "has_active", "balance_badge")
            response = super().changelist_view(request, extra_context)
            # Заменяем шаблон на частичный список результатов, чтобы не дублировать шапку
            try:
                response.template_name = 'admin/change_list_results.html'
            except Exception:
                pass
            return response
        # Не-HTMX: обычная страница
        self.list_display = ("id", "name", "phone", "pesel", "created_at", "balance_badge")
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        qs = qs.annotate(has_active=Exists(active_qs))
        return qs


@admin.register(Battery)
class BatteryAdmin(SimpleHistoryAdmin):
    # Убираем тяжёлые колонки roi_progress из списка, возвращаем в detail
    list_display = ("id", "short_code", "usage_now", "serial_number", "cost_price", "created_at")
    search_fields = ("short_code", "serial_number")

    def usage_now(self, obj):
        # Активные договоры сейчас, где батарея назначена
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        assignments = obj.assignments.select_related('rental__client').all()
        active_roots = []
        for a in assignments:
            start = timezone.localtime(a.start_at, tz)
            end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if start <= now and (end is None or end > now):
                root = a.rental.root if hasattr(a.rental, 'root') and a.rental.root_id else a.rental
                active_roots.append(root)
        # Уникальные root договоры
        uniq = []
        seen = set()
        for r in active_roots:
            if r.pk not in seen:
                uniq.append(r)
                seen.add(r.pk)
        parts = []
        for r in uniq:
            client_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_client_change', args=[r.client_id]), r.client.name)
            rental_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_rental_change', args=[r.pk]), r.contract_code)
            parts.append(format_html('[{}, {}]', client_link, rental_link))
        count = len(uniq)
        # Цвет + инлайн-стиль как fallback, если Bootstrap не подгрузился
        bg = 'secondary'
        bg_color = '#6c757d'
        if count == 1:
            bg = 'success'
            bg_color = '#198754'
        elif count > 1:
            bg = 'warning'
            bg_color = '#ffc107'
        content = format_html(', '.join(['{}'] * len(parts)), *parts) if parts else '-'
        return format_html('<span class="badge bg-{}" style="background-color:{}; color:#000;">{}</span>', bg, bg_color, content)
    usage_now.short_description = "В аренде"

    def roi_progress(self, obj):
        # Окупаемость по фактическим оплатам: распределяем оплаты по доле "нагрузки" батареи
        from decimal import Decimal, InvalidOperation
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        # Группируем по root-договорам, где батарея была назначена
        by_root_share = {}
        days_total = 0
        # Сначала соберём версии по root для быстрого доступа
        roots = {}
        for a in obj.assignments.select_related('rental').all():
            root = a.rental.root if getattr(a.rental, 'root_id', None) else a.rental
            roots.setdefault(root.pk, root)
        # Для каждого root считаем долю батареи (battery_share) и дни аренды
        for root in roots.values():
            versions = list(root.group_versions())
            # Precompute version windows with daily_rate
            v_windows = []
            for v in versions:
                v_start = timezone.localtime(v.start_at, tz)
                v_end = timezone.localtime(v.end_at, tz) if v.end_at else now
                v_windows.append((v_start, v_end, (v.weekly_rate or Decimal(0)) / Decimal(7)))
            battery_share = Decimal(0)
            # Соберём интервалы назначений этой батареи внутри данного root
            for a in obj.assignments.filter(rental__root=root).all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                # Идём по дням, считаем только те дни, когда есть активная версия
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    anchor = timezone.make_aware(datetime.combine(d, time(14, 0)), tz)
                    # Найти активную версию на этот anchor
                    rate = None
                    for v_start, v_end, v_rate in v_windows:
                        if v_start <= anchor and anchor < v_end and anchor <= now:
                            rate = v_rate
                            break
                    if rate is not None:
                        battery_share += rate
                    d += timedelta(days=1)
            # Считаем дни аренды без привязки к активной версии
            days_total = 0
            for a in obj.assignments.all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    days_total += 1
                    d += timedelta(days=1)
            # Общая сумма начислений по группе
            group_charges = root.group_charges_until(until=now) or Decimal(0)
            group_paid = root.group_paid_total() or Decimal(0)
            if group_charges > 0 and battery_share > 0:
                by_root_share[root.pk] = (battery_share, group_charges, group_paid)
        # Распределяем оплаты пропорционально
        allocated = Decimal(0)
        for battery_share, group_charges, group_paid in by_root_share.values():
            try:
                allocated += (battery_share / group_charges) * group_paid
            except (InvalidOperation, ZeroDivisionError):
                continue
        cost = obj.cost_price or Decimal(0)
        try:
            pct = int(round((allocated / cost) * 100)) if cost else 0
        except Exception:
            pct = 0
        # Цвета прогресса
        bar_class = 'bg-danger'
        bar_style = ''
        if pct >= 100:
            bar_class = 'bg-success'
        elif pct >= 75:
            bar_class = ''
            bar_style = 'background-color: orange;'
        elif pct >= 25:
            bar_class = 'bg-warning'
        width = min(max(pct, 0), 150)
        # Внутри бара показываем значение процента
        return format_html(
            '<div>'
            '<div class="progress" style="width:160px; height: 1rem;">'
            '<div class="progress-bar {}" role="progressbar" style="width: {}%; {};" aria-valuenow="{}" aria-valuemin="0" aria-valuemax="150">{}%</div>'
            '</div>'
            '<div style="font-size: 0.8rem; color: #666;">Дней в аренде: {}</div>'
            '</div>',
            bar_class, width, bar_style, pct, pct, days_total
        )
    roi_progress.short_description = "Окупаемость"



class RentalBatteryAssignmentForm(forms.ModelForm):
    class Meta:
        model = RentalBatteryAssignment
        fields = "__all__"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # поле видно, но не обязательно; если оставить пустым при создании — подставим старт договора
        if 'start_at' in self.fields:
            self.fields['start_at'].required = False
    def clean(self):
        cd = super().clean()
        start = cd.get('start_at')
        if not start:
            rental = getattr(self.instance, 'rental', None)
            if rental and getattr(rental, 'start_at', None):
                cd['start_at'] = rental.start_at
                self.cleaned_data['start_at'] = rental.start_at
        return cd

class RentalBatteryAssignmentInline(admin.TabularInline):
    model = RentalBatteryAssignment
    form = RentalBatteryAssignmentForm
    extra = 0
    readonly_fields = ("created_by", "updated_by")
    autocomplete_fields = ("battery",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            field = formset.form.base_fields.get('created_by')
            if field:
                field.queryset = User.objects.filter(is_staff=True).order_by('username')
                field.label = "Кто принял деньги"
                if request.user.is_superuser:
                    field.required = True
                else:
                    field.initial = request.user.pk
                    field.disabled = True
                    field.help_text = "Доступно только суперпользователю"
        except Exception:
            pass
        return formset


class NewVersionActionForm(ActionForm):
    new_weekly_rate = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, label="Новая недельная ставка (PLN)"
    )
    new_start_at = forms.DateTimeField(required=False, label="Начало новой версии", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    free_days = forms.IntegerField(required=False, min_value=0, label="Бесплатные дни")
    payment_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма оплаты")
    payment_method = forms.ChoiceField(required=False, choices=[('cash','Наличные'),('blik','BLIK'),('revolut','Revolut'),('other','Другое')], label="Метод оплаты")
    payment_note = forms.CharField(required=False, label="Примечание к оплате")
    deposit_return_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма возврата депозита")
    deposit_return_note = forms.CharField(required=False, label="Примечание к возврату депозита")


@admin.register(Rental)
class RentalAdmin(SimpleHistoryAdmin):
    autocomplete_fields = ('client',)

    def changelist_view(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        from .models import Client
        # Используем только необходимые поля, чтобы не тянуть всё
        extra_context['clients'] = Client.objects.only('id', 'name').order_by('name')
        return super().changelist_view(request, extra_context=extra_context)

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class CustomChangeList(ChangeList):
            def get_results(self, request):
                super().get_results(request)
                # Приглушить строки с статусом modified или closed
                for result in self.result_list:
                    if hasattr(result, 'status') and result.status in [result.Status.MODIFIED, result.Status.CLOSED]:
                        result.row_class = 'opacity-80'

        return CustomChangeList

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Предзагрузить связанные объекты, чтобы избежать N+1
        from django.db.models import Count
        qs = qs.select_related('client').prefetch_related('assignments', 'assignments__battery')
        qs = qs.annotate(assignments_count=Count('assignments'))
        # Добавить row_class для приглушения строк
        for obj in qs:
            if obj.status in [obj.Status.MODIFIED, obj.Status.CLOSED]:
                obj.row_class = 'opacity-80'
            else:
                obj.row_class = ''
        return qs

    class Media:
        css = {
            'all': ('admin/css/custom.css',)
        }

    list_display = (
        "id", "contract_code", "version", "client", "start_at", "end_at",
        "weekly_rate", "status", "assigned_batteries_short",
    )
    list_filter = ("status",)
    list_per_page = 25  # Ограничение записей на странице для ускорения отображения


    search_fields = ("client__name", "contract_code")
    inlines = [RentalBatteryAssignmentInline, PaymentInline]

    readonly_fields = ("group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now", "created_by", "updated_by")
    def batteries_count_now(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        count = 0
        batteries = []
        for a in obj.assignments.all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                count += 1
                batteries.append(a.battery.short_code)
        obj._batteries_list = batteries
        return count

    def assigned_batteries_short(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        codes = []
        for a in obj.assignments.select_related('battery').all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                codes.append(a.battery.short_code)
        if obj.status in [obj.Status.ACTIVE, obj.Status.MODIFIED]:
            if codes:
                return format_html(' '.join(['<span class="badge bg-secondary me-1">{}</span>'] * len(codes)), *codes)
            else:
                return mark_safe('<span class="text-muted">—</span>')
        if obj.status == obj.Status.CLOSED:
            return mark_safe('<span class="text-muted">—</span>')
        return ''

    assigned_batteries_short.short_description = "Батареи"


    action_form = NewVersionActionForm
    actions = ["make_new_version", "close_with_deposit"]
    
    def get_list_display(self, request):
        base = list(super().get_list_display(request)) if hasattr(super(), 'get_list_display') else list(self.list_display)
        # вставим количество батарей рядом с агрегатами
        if "batteries_count_now" not in base:
            base = list(self.list_display)
        return tuple(base)

    def fmt_pln(self, value):
        try:
            return f"{value:.2f} PLN"
        except Exception:
            return value

    def assigned_batteries_short(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        codes = []
        for a in obj.assignments.select_related('battery').all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                codes.append(a.battery.short_code)
        if obj.status in [obj.Status.ACTIVE, obj.Status.MODIFIED]:
            if codes:
                # badges for active or modified
                return format_html(' '.join(['<span class="badge bg-secondary me-1">{}</span>'] * len(codes)), *codes)
            else:
                return mark_safe('<span class="text-muted">—</span>')
        if obj.status == obj.Status.CLOSED:
            return mark_safe('<span class="text-muted">—</span>')
        return ''
    assigned_batteries_short.short_description = "Батареи"

    def group_charges_now(self, obj):
        return self.fmt_pln(obj.group_charges_until(until=timezone.now()))
    group_charges_now.short_description = "Начислено"

    def group_paid_total(self, obj):
        return self.fmt_pln(obj.group_paid_total())
    group_paid_total.short_description = "Оплачено"

    def group_deposit_total(self, obj):
        return self.fmt_pln(obj.group_deposit_total())
    group_deposit_total.short_description = "Депозит"

    def group_balance_now(self, obj):
        now = timezone.now()
        charges = obj.group_charges_until(until=now)
        paid = obj.group_paid_total()
        return self.fmt_pln(paid - charges)

    group_balance_now.short_description = "Баланс"

    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, 'created_by_id', None):
            obj.created_by = request.user
        obj.updated_by = request.user
        # проставляем имена для Supabase
        if hasattr(obj, 'created_by_name') and obj.created_by and not obj.created_by_name:
            obj.created_by_name = request.user.get_full_name() or request.user.username or request.user.email
        if hasattr(obj, 'updated_by_name'):
            obj.updated_by_name = request.user.get_full_name() or request.user.username or request.user.email
        super().save_model(request, obj, form, change)
        
        # Отобразить человеку сразу обновленные агрегаты
        self.message_user(request, f"Баланс: {self.group_balance_now(obj)}; Начислено: {self.group_charges_now(obj)}; Оплачено: {self.group_paid_total(obj)}; Депозит: {self.group_deposit_total(obj)}")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            # Default start_at to rental.start_at if not provided in inline
            if hasattr(inst, "start_at") and not inst.start_at:
                parent_start = getattr(form.instance, "start_at", None)
                if parent_start:
                    inst.start_at = parent_start
            if hasattr(inst, "created_by") and not inst.pk:
                inst.created_by = request.user
            if hasattr(inst, "updated_by"):
                inst.updated_by = request.user
            inst.save()
        formset.save_m2m()

    def make_new_version(self, request, queryset):
        count = 0
        # Получаем ставку из формы действий
        rate_str = request.POST.get("new_weekly_rate")
        new_rate = None
        # Получаем дату и время из формы (новое поле)
        new_start = None
        if request.POST.get("new_start_at"):
            try:
                # получаем datetime-local => 'YYYY-MM-DDTHH:MM'
                new_start = timezone.datetime.fromisoformat(request.POST.get("new_start_at").replace('T', ' '))
                if timezone.is_naive(new_start):
                    new_start = timezone.make_aware(new_start, timezone.get_current_timezone())
            except Exception:
                new_start = None
        # Получаем бесплатные дни
        free_days_str = request.POST.get("free_days")
        free_days = 0
        if free_days_str:
            try:
                free_days = int(free_days_str)
            except Exception:
                free_days = 0
        if rate_str:
            try:
                new_rate = Decimal(rate_str)
            except Exception:
                new_rate = None
        for rental in queryset:
            root = rental.root or rental
            now = new_start or timezone.now()
            # Закрываем старую версию
            if not rental.end_at or rental.end_at > now:
                rental.end_at = now
            rental.status = Rental.Status.MODIFIED
            rental.save()
            if free_days > 0:
                # Создаем версию с бесплатными днями
                free_start = now
                free_end = free_start + timezone.timedelta(days=free_days)
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                free_version = Rental(
                    client=rental.client,
                    start_at=free_start,
                    end_at=free_end,
                    weekly_rate=Decimal(0),
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                free_version.created_by = request.user
                free_version.updated_by = request.user
                free_version.save()
                # Создаем следующую версию после бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = free_version.version + 1
                next_start = free_end
                new_rental = Rental(
                    client=rental.client,
                    start_at=next_start,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=free_version,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 2
            else:
                # Создаем новую версию без бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                new_rental = Rental(
                    client=rental.client,
                    start_at=now,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 1
        self.message_user(request, f"Создано новых версий: {count}; активные батареи перенесены")
    make_new_version.short_description = "Создать новую версию (начало с даты и времени, с переносом батарей)"

    # Пользовательский admin-view для изменения состава батарей
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/change-batteries/',
                self.admin_site.admin_view(self.change_batteries_view),
                name='rental_rental_change_batteries',
            )
        ]
        return custom + urls

    def change_batteries_view(self, request, pk):
        rental = Rental.objects.get(pk=pk)
        AssignmentFormSet = inlineformset_factory(
            Rental,
            RentalBatteryAssignment,
            form=RentalBatteryAssignmentForm,
            extra=0,
            can_delete=True,
            fields=('battery', 'start_at', 'end_at'),
        )
        if request.method == 'POST':
            formset = AssignmentFormSet(request.POST, instance=rental)
            if formset.is_valid():
                instances = formset.save(commit=False)
                # Валидация: после сохранения должно остаться >=1 активное назначение сейчас или в будущем
                for inst in instances:
                    if not getattr(inst, 'created_by_id', None):
                        inst.created_by = request.user
                    inst.updated_by = request.user
                    inst.save()
                for obj in formset.deleted_objects:
                    obj.delete()
                # Проверка минимума одной батареи ("на сейчас")
                tz = timezone.get_current_timezone()
                now = timezone.now()
                active = 0
                for a in rental.assignments.select_related('battery').all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_start <= now and (a_end is None or a_end > now):
                        active += 1
                if active <= 0:
                    messages.error(request, "Должна быть назначена минимум одна батарея на текущий момент")
                else:
                    messages.success(request, "Состав батарей обновлён")
                    return TemplateResponse(request, 'admin/rental/change_batteries_done.html', {'rental': rental})
            else:
                messages.error(request, "Исправьте ошибки в форме")
        else:
            formset = AssignmentFormSet(instance=rental)
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            rental=rental,
            title=f"Изменение батарей: договор {rental.contract_code} v{rental.version}",
            formset=formset,
        )
        return TemplateResponse(request, 'admin/rental/change_batteries.html', context)

    def close_with_deposit(self, request, queryset):
        closed = 0
        # Опционально: принять оплату (аренда) сразу из формы действия
        amt = request.POST.get("payment_amount")
        mth = request.POST.get("payment_method")
        note = request.POST.get("payment_note")
        for rental in queryset:
            root = rental.root or rental
            now = timezone.now()
            for v in Rental.objects.filter(root=root, status=Rental.Status.ACTIVE):
                if not v.end_at or v.end_at > now:
                    v.end_at = now
                v.status = Rental.Status.CLOSED
                v.save()
            balance = root.group_balance(until=now)
            deposit_left = root.group_deposit_total()
            applied = Decimal(0)
            if balance > 0 and deposit_left > 0:
                applied = min(balance, deposit_left)
                Payment.objects.create(
                    rental=root,
                    amount=-applied,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.ADJUSTMENT,
                    method=Payment.Method.OTHER,
                    note="Зачёт депозита при закрытии",
                    created_by=request.user,
                    updated_by=request.user,
                )
                balance -= applied
                deposit_left -= applied
            if deposit_left > 0:
                Payment.objects.create(
                    rental=root,
                    amount=deposit_left,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.RETURN_DEPOSIT,
                    method=Payment.Method.OTHER,
                    note="Возврат остатка депозита",
                    created_by=request.user,
                    updated_by=request.user,
                )
            if amt:
                try:
                    amt_dec = Decimal(amt)
                    if amt_dec != 0:
                        Payment.objects.create(
                            rental=root,
                            amount=amt_dec,
                            date=timezone.localdate(),
                            type=Payment.PaymentType.RENT,
                            method=mth or Payment.Method.OTHER,
                            note=note or "",
                            created_by=request.user,
                            updated_by=request.user,
                        )
                except Exception:
                    pass
            closed += 1
        self.message_user(request, f"Закрыто договоров: {closed}")
    close_with_deposit.short_description = "Закрыть договор (с зачётом депозита)"


@admin.register(Payment)
class PaymentAdmin(SimpleHistoryAdmin):
    class RentalFilter(AutocompleteFilter):
        title = 'Договор'
        field_name = 'rental'

    list_display = ("id", "rental", "date", "amount", "type", "method", "created_by_name")
    list_filter = (RentalFilter, "type", "method")
    search_fields = ("rental__id", "note", "rental__client__name", "created_by__username")
    readonly_fields = ("updated_by",)
    date_hierarchy = 'date'
    list_per_page = 50


    def changelist_view(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        from .models import Rental
        rid = request.GET.get('rental__id__exact')
        if rid:
            try:
                extra_context['selected_rental'] = Rental.objects.select_related('client').only('id','contract_code','client__name').get(pk=rid)
            except Rental.DoesNotExist:
                extra_context['selected_rental'] = None
        return super().changelist_view(request, extra_context=extra_context)

    def get_search_results(self, request, queryset, search_term):
        # Ограничение базового поиска по платежам — оставляем стандартное поведение
        return super().get_search_results(request, queryset, search_term)


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('rental__client', 'created_by')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        field = form.base_fields.get('created_by')
        if field:
            field.queryset = User.objects.filter(is_staff=True).order_by('username')
            field.label = "Кто принял деньги"
            if request.user.is_superuser:
                field.required = True
                field.disabled = False
            else:
                field.initial = request.user.pk
                field.disabled = True
                field.help_text = "Доступно только суперпользователю"
        return form

    @admin.display(ordering='created_by__username', description='Кто ввёл запись')
    def created_by_name(self, obj):
        user = obj.created_by
        if not user:
            return ''
        return user.username

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            # Для несуперпользователя всегда фиксируем автора как текущего
            obj.created_by = request.user
        elif not getattr(obj, 'created_by_id', None):
            # Для суперпользователя, если поле не выбрано, используем текущего
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name")


@admin.register(Expense)
class ExpenseAdmin(SimpleHistoryAdmin):
    list_display = ("id", "date", "amount", "category", "paid_source", "paid_by_partner")
    list_filter = ("category", "paid_source")
    search_fields = ("note", "description")
    autocomplete_fields = ("paid_by_partner",)


@admin.register(Repair)
class RepairAdmin(SimpleHistoryAdmin):
    list_display = ("id", "battery", "start_at", "end_at", "cost")


@admin.register(BatteryStatusLog)
class BatteryStatusLogAdmin(SimpleHistoryAdmin):
    list_display = ("id", "battery", "kind", "start_at", "end_at")
