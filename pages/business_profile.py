"""Streamlit page presenting existing transactions as a business cash-flow profile."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from modules.analysis import (
    calculate_merchant_totals,
    calculate_spending_trend,
    compute_anomaly_report,
)
from utils import session as session_utils
from utils.ui_components import responsive_width_kwargs


def render() -> None:
    """Render an aggregate view of existing transactions for sole proprietors
    and freelancers who track their business flow through WeFinance."""
    i18n = session_utils.get_i18n()
    st.title(i18n.t("business_profile.title"))
    st.write(i18n.t("business_profile.description"))

    transactions = session_utils.get_transactions()
    if not transactions:
        st.warning(i18n.t("business_profile.require_upload"))
        return

    trend_monthly = calculate_spending_trend(transactions, frequency="M")
    merchant_totals = calculate_merchant_totals(transactions)
    anomaly_report = compute_anomaly_report(
        transactions,
        whitelist_merchants=session_utils.get_trusted_merchants(),
    )

    with st.expander(i18n.t("business_profile.trend_title"), expanded=True):
        if not trend_monthly.empty:
            fig = px.bar(
                trend_monthly,
                x="period",
                y="amount",
                title=i18n.t("business_profile.trend_title"),
                labels={
                    "period": i18n.t("spending.label_month"),
                    "amount": i18n.t("spending.label_amount"),
                },
            )
            fig.update_layout(margin=dict(t=40, b=40, l=40, r=0))
            st.plotly_chart(fig, **responsive_width_kwargs(st.plotly_chart))
        else:
            st.info(i18n.t("business_profile.trend_empty"))

    with st.expander(i18n.t("business_profile.concentration_title"), expanded=True):
        if merchant_totals:
            total = sum(merchant_totals.values())
            rows = sorted(merchant_totals.items(), key=lambda kv: kv[1], reverse=True)[
                :10
            ]
            table = pd.DataFrame(
                [
                    {
                        i18n.t("business_profile.label_merchant"): (
                            name or i18n.t("business_profile.label_unknown")
                        ),
                        i18n.t("spending.label_amount"): amount,
                        i18n.t("business_profile.label_share"): (
                            f"{amount / total * 100:.1f}%" if total else "0.0%"
                        ),
                    }
                    for name, amount in rows
                ]
            )
            st.dataframe(
                table, hide_index=True, **responsive_width_kwargs(st.dataframe)
            )
            top_share = (rows[0][1] / total * 100) if total and rows else 0.0
            if top_share >= 40:
                st.info(
                    i18n.t(
                        "business_profile.concentration_warning",
                        share=f"{top_share:.0f}",
                    )
                )
        else:
            st.info(i18n.t("business_profile.concentration_empty"))

    with st.expander(i18n.t("business_profile.anomaly_title"), expanded=True):
        items = anomaly_report.get("items", [])
        if items:
            for item in items:
                date_str = item.get("date") or "-"
                merchant = item.get("merchant") or i18n.t(
                    "business_profile.label_unknown"
                )
                amount = item.get("amount", 0.0)
                reason = item.get("reason", "")
                st.warning(
                    i18n.t(
                        "app.anomaly_info",
                        date=date_str,
                        merchant=merchant,
                        amount=f"{float(amount):,.2f}",
                    )
                )
                if reason:
                    st.caption(reason)
        else:
            message_key = anomaly_report.get("message")
            if message_key:
                st.info(i18n.t(message_key))
            else:
                st.info(i18n.t("business_profile.anomaly_none"))

    st.caption(i18n.t("business_profile.footer_note"))


if __name__ == "__main__":  # pragma: no cover - streamlit entry point
    render()
