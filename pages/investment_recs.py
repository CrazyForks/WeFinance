"""Investment recommendation and explainability view."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

from models.entities import Recommendation, Transaction
from services.recommendation_service import RecommendationService
from utils import session as session_utils
from utils.session import get_i18n, get_monthly_budget, set_product_recommendations
from utils.ui_components import (
    render_financial_health_card,
    responsive_width_kwargs,
)

# 高级问卷选项数量常量，便于统一维护
QUESTION_OPTION_COUNT = 3


def _normalize_question_options(raw_options: Iterable[Any]) -> List[Tuple[str, int]]:
    """将不同格式的选项统一为(label, score)结构，避免LLM输出差异导致崩溃"""

    normalized: List[Tuple[str, int]] = []
    for option in raw_options or []:
        label: str | None = None
        score_value: Any = None

        if isinstance(option, dict):
            label = option.get("label") or option.get("text") or option.get("option")
            score_value = option.get("score") or option.get("value")
        elif isinstance(option, (list, tuple)) and len(option) >= 2:
            label = str(option[0])
            score_value = option[1]
        else:
            continue

        if not label:
            continue

        try:
            score_int = int(score_value)
        except (TypeError, ValueError):
            continue

        normalized.append((str(label), score_int))

    if len(normalized) < QUESTION_OPTION_COUNT:
        return []
    return normalized[:QUESTION_OPTION_COUNT]


# 简化版风险问题（LLM生成失败时的后备方案）
FALLBACK_QUESTIONS: List[Dict[str, object]] = [
    {
        "id": "q1",
        "prompt": "您能接受的最大亏损是多少？",
        "options": [
            ("5%以内，几乎不能亏损", 1),
            ("10%左右，可接受一定波动", 2),
            ("20%以上，只要长期有收益", 3),
        ],
    },
    {
        "id": "q2",
        "prompt": "您的投资期限是多久？",
        "options": [
            ("1年以内，需要资金的流动性", 1),
            ("1-3年，可以阶段性锁定资金", 2),
            ("3年以上，长期增值为主", 3),
        ],
    },
]


@st.cache_data(show_spinner=False)
def _generate_cached_recommendation(
    transactions_dump: Tuple[Tuple[Tuple[str, object], ...], ...],
    responses_tuple: Tuple[Tuple[str, int], ...],
    goal: str,
    locale: str,
) -> Dict[str, object]:
    """Cacheable wrapper producing recommendation payload."""
    service = RecommendationService()
    transactions = [Transaction(**dict(entry)) for entry in transactions_dump]
    responses = dict(responses_tuple)
    result = service.generate(
        transactions=transactions,
        responses=responses,
        investment_goal=goal,
        locale=locale,
    )
    recs = result.get("recommendations", [])
    serialized = []
    for rec in recs:
        if isinstance(rec, Recommendation):
            serialized.append(rec.model_dump())
        elif isinstance(rec, dict):
            serialized.append(rec)
    result["recommendations"] = serialized
    return result


def _collect_risk_answers(
    questions: List[Dict[str, object]],
    guidance_header: str,
    goal_guidance: str,
) -> Tuple[Dict[str, int], str]:
    """收集风险评估问卷答案（问题由LLM动态生成）"""
    i18n = get_i18n()

    # 显示LLM生成的引导文案
    st.markdown(f"#### {guidance_header}")

    answers: Dict[str, int] = {}
    for idx, question in enumerate(questions):
        question_id = question.get("id") or f"advanced_{idx}"
        key = f"risk_advanced_{question_id}_{idx}"  # 确保key唯一
        prompt = (
            question.get("prompt")
            or question.get("question")
            or question.get("title")
            or f"问题 {idx + 1}"
        )

        normalized_options = _normalize_question_options(question.get("options", []))
        if not normalized_options:
            st.warning(
                f"⚠️ {prompt} 选项加载异常，已为您跳过。"
                if i18n.locale == "zh_CN"
                else f"⚠️ Options missing for: {prompt}"
            )
            continue

        option_labels = [opt_label for opt_label, _ in normalized_options]
        selected = st.radio(
            prompt,
            options=option_labels,
            index=0,
            key=key,
            horizontal=False,
        )

        for opt_label, score in normalized_options:
            if opt_label == selected:
                answers[str(question_id)] = score
                break

    # 显示LLM生成的目标引导文案
    st.markdown(f"#### {goal_guidance}")
    goal = st.text_input(
        i18n.t("recommendation.prompt_goal"),
        placeholder=i18n.t("recommendation.goal_placeholder"),
        key="investment_goal_advanced",  # 区别于快速模式的key
    )
    return answers, goal


@st.cache_data(show_spinner=False)
def _generate_guidance_text(
    locale: str,
    monthly_avg: float,
    budget: float,
    investable: float,
) -> Tuple[str, str]:
    """生成引导文案（LLM动态生成）"""
    from utils.error_handling import safe_call
    from openai import OpenAI
    import os
    import json

    @safe_call(timeout=15, fallback=None, error_message="引导文案生成失败")
    def _call_llm():
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

        prompt = f"""你是一位专业的理财顾问，正在引导用户进行风险评估和投资规划。

用户财务状况：
- 月均支出：¥{monthly_avg:.0f}
- 月度预算：¥{budget:.0f}
- 可投资金额：¥{investable:.0f}

请生成两段引导文案：
1. 风险评估引导（10-15字）：引导用户了解自己的风险承受能力
2. 投资目标引导（10-15字）：引导用户明确投资目标

要求：
- 语言自然、亲切、专业
- 不使用"步骤1"、"步骤2"这种机械化表述
- 根据用户财务状况提供针对性引导

返回JSON格式：
{{
  "risk_guidance": "风险评估引导文案",
  "goal_guidance": "投资目标引导文案"
}}
"""

        if locale == "en_US":
            prompt = f"""You are a professional financial advisor guiding users through risk assessment and investment planning.

User's financial situation:
- Monthly spending: ${monthly_avg:.0f}
- Monthly budget: ${budget:.0f}
- Investable amount: ${investable:.0f}

Generate two guidance texts:
1. Risk assessment guidance (10-15 words): Guide users to understand their risk tolerance
2. Investment goal guidance (10-15 words): Guide users to clarify investment goals

Requirements:
- Natural, friendly, professional language
- Don't use mechanical phrases like "Step 1", "Step 2"
- Provide targeted guidance based on user's financial situation

Return JSON format:
{{
  "risk_guidance": "Risk assessment guidance text",
  "goal_guidance": "Investment goal guidance text"
}}
"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "你是专业的理财顾问，擅长用简洁亲切的语言引导用户。",
                },
                {"role": "user", "content": prompt},
            ],
            timeout=15,
        )

        content = response.choices[0].message.content or ""
        # 清理markdown代码块
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
        return data.get("risk_guidance", ""), data.get("goal_guidance", "")

    result = _call_llm()
    if result and result[0] and result[1]:
        return result

    # 后备方案
    i18n = get_i18n()
    return (
        i18n.t("recommendation.step1") if locale == "zh_CN" else "Risk Assessment",
        i18n.t("recommendation.step2") if locale == "zh_CN" else "Investment Goal",
    )


def _render_results(results: Dict[str, object]) -> None:
    i18n = get_i18n()
    recommendations_raw = results.get("recommendations", [])
    recommendations = [
        rec if isinstance(rec, Recommendation) else Recommendation(**rec)
        for rec in recommendations_raw
    ]
    profile: Dict[str, object] = results.get("financial_profile", {})  # type: ignore[assignment]
    risk_level: str = results.get("risk_level", "")  # type: ignore[assignment]

    st.success(i18n.t("recommendation.risk_result", risk=risk_level))

    st.subheader(i18n.t("recommendation.financial_profile_title"))
    col1, col2, col3 = st.columns(3)
    monthly_avg = float(profile.get("monthly_average", 0.0) or 0.0)
    volatility = float(profile.get("spending_volatility", 0.0) or 0.0)
    investable = float(profile.get("investable_amount", 0.0) or 0.0)
    with col1:
        st.metric(
            i18n.t("recommendation.metric_monthly_avg"),
            f"{i18n.currency_symbol}{monthly_avg:,.0f}",
        )
    with col2:
        st.metric(
            i18n.t("recommendation.metric_investable"),
            f"{i18n.currency_symbol}{investable:,.0f}",
        )
    with col3:
        st.metric(
            i18n.t("recommendation.metric_volatility"), f"{volatility * 100:.1f}%"
        )

    breakdown: Dict[str, float] = profile.get("category_breakdown", {})  # type: ignore[assignment]
    if breakdown:
        st.subheader(i18n.t("recommendation.category_breakdown_title"))
        df = pd.DataFrame(
            [
                {"category": cat, "share": share * 100}
                for cat, share in breakdown.items()
            ]
        )
        fig = px.bar(
            df,
            x="category",
            y="share",
            text="share",
            labels={
                "category": i18n.t("spending.label_category"),
                "share": i18n.t("recommendation.label_ratio"),
            },
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(yaxis_title=i18n.t("recommendation.label_ratio"))
        st.plotly_chart(fig, **responsive_width_kwargs(st.plotly_chart))

    st.subheader(i18n.t("recommendation.recommendation_list_title"))
    for rec in recommendations:
        st.markdown(f"### {rec.title}")
        st.write(rec.summary)
        for idx, step in enumerate(rec.rationale_steps, start=1):
            st.write(f"{idx}. {step}")

    # 详细报告生成部分
    st.markdown("---")
    st.subheader(
        "📊 生成详细理财报告"
        if st.session_state.get("locale") == "zh_CN"
        else "📊 Generate Detailed Financial Report"
    )
    st.caption(
        "基于您的真实消费数据，生成3000-5000字的专业理财咨询报告，包含财务分析、风险评估、资产配置策略、执行计划等完整内容。"
        if st.session_state.get("locale") == "zh_CN"
        else "Generate a comprehensive 3000-5000 word professional financial advisory report based on your transaction data, including financial analysis, risk assessment, asset allocation strategy, and execution plan."
    )

    if st.button(
        (
            "🚀 生成详细报告（使用GPT-4o完整模型）"
            if st.session_state.get("locale") == "zh_CN"
            else "🚀 Generate Detailed Report (GPT-4o)"
        ),
        type="primary",
        key="generate_detailed_report",
    ):
        # 从session_state获取必要数据
        transactions = session_utils.get_transactions()
        responses = st.session_state.get("risk_responses", {})
        investment_goal = st.session_state.get("investment_goal", "")
        risk_profile_key = st.session_state.get("risk_profile_key", "balanced")

        with st.spinner(
            "正在生成详细报告，这可能需要30-60秒..."
            if st.session_state.get("locale") == "zh_CN"
            else "Generating detailed report, this may take 30-60 seconds..."
        ):
            service = RecommendationService()
            detailed_report = service.generate_detailed_report(
                transactions=transactions,
                responses=responses,
                investment_goal=investment_goal,
                risk_profile=risk_profile_key,
                metrics=profile,  # type: ignore[arg-type]
                locale=st.session_state.get("locale", "en_US"),
            )

            if detailed_report:
                st.session_state["detailed_financial_report"] = detailed_report
                st.success(
                    "✅ 详细报告生成成功！"
                    if st.session_state.get("locale") == "zh_CN"
                    else "✅ Report generated successfully!"
                )
            else:
                st.error(
                    "❌ 报告生成失败，请稍后重试。"
                    if st.session_state.get("locale") == "zh_CN"
                    else "❌ Report generation failed, please try again later."
                )

    # 显示已生成的详细报告
    if (
        "detailed_financial_report" in st.session_state
        and st.session_state["detailed_financial_report"]
    ):
        st.markdown("---")
        st.markdown(
            "## 📄 详细理财咨询报告"
            if st.session_state.get("locale") == "zh_CN"
            else "## 📄 Detailed Financial Advisory Report"
        )

        # 提供下载按钮
        report_content = st.session_state["detailed_financial_report"]
        st.download_button(
            label=(
                "💾 下载报告（Markdown格式）"
                if st.session_state.get("locale") == "zh_CN"
                else "💾 Download Report (Markdown)"
            ),
            data=report_content,
            file_name=f"financial_report_{pd.Timestamp.now().strftime('%Y%m%d')}.md",
            mime="text/markdown",
            key="download_report",
        )

        # 渲染Markdown报告
        st.markdown(report_content)


def render() -> None:
    """Render investment recommendation workflow with XAI explanation."""
    i18n = get_i18n()
    st.title(i18n.t("recommendation.title"))
    st.write(i18n.t("recommendation.subtitle"))

    transactions = session_utils.get_transactions()
    if not transactions:
        st.warning(i18n.t("recommendation.require_upload"))
        return

    # 显示财务健康卡片（整合预算与支出）
    render_financial_health_card(transactions)

    # 获取用户预算和财务状况
    budget = get_monthly_budget()
    locale = st.session_state.get("locale", "en_US")

    # === 简化流程：单步输入模式 ===
    st.markdown("---")
    st.markdown(
        "### 💡 快速理财规划"
        if locale == "zh_CN"
        else "### 💡 Quick Financial Planning"
    )
    st.caption(
        "无需复杂问卷，直接告诉我您的理财目标，AI将为您生成个性化的详细理财方案。"
        if locale == "zh_CN"
        else "Skip the questionnaire - just tell us your goal and get a personalized financial plan."
    )

    # 智能目标输入（带示例）
    goal_input = st.text_area(
        (
            "📝 请描述您的理财目标"
            if locale == "zh_CN"
            else "📝 Describe your financial goal"
        ),
        placeholder=(
            (
                "示例：\n"
                "• 我想在3年内存够20万首付买房\n"
                "• 长期投资，希望每年收益10%以上\n"
                "• 为孩子准备50万教育金，10年后使用\n"
                "• 退休养老规划，需要稳健增值"
            )
            if locale == "zh_CN"
            else (
                "Examples:\n"
                "• Save $200k for house down payment in 3 years\n"
                "• Long-term investment with 10%+ annual return\n"
                "• $500k education fund for child in 10 years\n"
                "• Retirement planning with stable growth"
            )
        ),
        height=120,
        key="quick_goal_input",
    )

    # 风险偏好选择（简化为单选）
    risk_preference = st.radio(
        "💼 您的风险偏好" if locale == "zh_CN" else "💼 Risk Preference",
        options=[
            (
                "保守型（不能接受本金亏损）"
                if locale == "zh_CN"
                else "Conservative (No principal loss)"
            ),
            (
                "稳健型（可接受小幅波动）"
                if locale == "zh_CN"
                else "Balanced (Moderate volatility)"
            ),
            (
                "进取型（追求高收益，可接受较大波动）"
                if locale == "zh_CN"
                else "Aggressive (High return, high volatility)"
            ),
        ],
        index=1,
        key="quick_risk_preference",
        horizontal=True,
    )

    # 一键生成详细报告
    if st.button(
        (
            "🚀 生成专业理财报告（3000-5000字深度分析）"
            if locale == "zh_CN"
            else "🚀 Generate Professional Report (3000-5000 words)"
        ),
        type="primary",
        disabled=not goal_input.strip(),
        key="generate_quick_report",
    ):
        # 映射风险偏好到profile key
        if "保守" in risk_preference or "Conservative" in risk_preference:
            risk_profile_key = "conservative"
        elif "进取" in risk_preference or "Aggressive" in risk_preference:
            risk_profile_key = "aggressive"
        else:
            risk_profile_key = "balanced"

        with st.spinner(
            "正在生成详细报告，预计需要30-60秒..."
            if locale == "zh_CN"
            else "Generating report, estimated 30-60 seconds..."
        ):
            try:
                service = RecommendationService()

                # 先分析财务指标
                metrics = service.analyze_transactions(transactions)

                # 直接生成详细报告（跳过问卷流程）
                detailed_report = service.generate_detailed_report(
                    transactions=transactions,
                    responses={},  # 无需问卷数据
                    investment_goal=goal_input.strip(),
                    risk_profile=risk_profile_key,
                    metrics=metrics,
                    locale=locale,
                )

                if detailed_report:
                    st.session_state["detailed_financial_report"] = detailed_report
                    st.session_state["investment_goal"] = goal_input.strip()
                    st.session_state["risk_profile_key"] = risk_profile_key
                    st.success(
                        "✅ 报告生成成功！"
                        if locale == "zh_CN"
                        else "✅ Report generated!"
                    )
                    st.rerun()
                else:
                    st.error(
                        "❌ 报告生成失败，请检查网络连接或稍后重试。"
                        if locale == "zh_CN"
                        else "❌ Failed to generate report."
                    )
            except Exception as exc:
                st.error(
                    f"❌ 生成失败：{exc}"
                    if locale == "zh_CN"
                    else f"❌ Generation failed: {exc}"
                )

    # 显示已生成的详细报告（仅当尚未有资产配置结果时避免重复展示）
    if (
        "detailed_financial_report" in st.session_state
        and st.session_state["detailed_financial_report"]
        and not st.session_state.get("recommendation_explanation")
    ):
        st.markdown("---")
        st.markdown(
            "## 📄 详细理财咨询报告"
            if locale == "zh_CN"
            else "## 📄 Detailed Financial Report"
        )

        # 提供下载按钮
        report_content = st.session_state["detailed_financial_report"]
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(
                f"基于您的目标：{st.session_state.get('investment_goal', '')} | 风险偏好：{st.session_state.get('risk_profile_key', '')}型"
            )
        with col2:
            st.download_button(
                label="💾 下载报告" if locale == "zh_CN" else "💾 Download",
                data=report_content,
                file_name=f"financial_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                key="download_report",
                **responsive_width_kwargs(st.download_button),
            )

        # 渲染Markdown报告
        st.markdown(report_content)

    # 已存在的资产配置结果（来自高级模式）
    persisted_results = st.session_state.get("recommendation_explanation")
    if persisted_results:
        st.markdown("---")
        _render_results(persisted_results)

    # === 高级模式：保留完整问卷流程（折叠） ===
    with st.expander(
        (
            "🔧 高级模式：完整风险评估问卷（可选）"
            if locale == "zh_CN"
            else "🔧 Advanced mode: full risk assessment questionnaire (optional)"
        ),
        expanded=False,
    ):
        st.caption(
            "适合需要精细化风险评估的用户，通过多维度问卷深度分析您的风险承受能力。"
            if locale == "zh_CN"
            else "For users who need detailed risk assessment through multi-dimensional questionnaire."
        )

        # 生成个性化问题（LLM动态生成）
        with st.spinner(
            i18n.t("common.loading") if locale == "zh_CN" else "Loading..."
        ):
            service = RecommendationService()
            questions = service.generate_personalized_questions(
                transactions=transactions,
                budget=budget,
                locale=locale,
            )

        # 如果LLM生成失败，使用后备问题
        if not questions:
            st.info(
                "使用简化版问卷（智能问题生成暂时不可用）"
                if locale == "zh_CN"
                else "Using simplified questionnaire"
            )
            questions = FALLBACK_QUESTIONS

        # 计算财务指标用于生成引导文案
        metrics = service.analyze_transactions(transactions)
        monthly_avg = float(metrics.get("monthly_average", 0.0) or 0.0)
        investable = float(metrics.get("investable_amount", 0.0) or 0.0)

        # 生成引导文案
        risk_guidance, goal_guidance = _generate_guidance_text(
            locale=locale,
            monthly_avg=monthly_avg,
            budget=budget,
            investable=investable,
        )

        # 收集用户答案
        answers, goal = _collect_risk_answers(questions, risk_guidance, goal_guidance)
        responses_tuple = tuple(sorted(answers.items()))
        transactions_dump = tuple(
            tuple(sorted(tx.model_dump().items(), key=lambda item: item[0]))
            for tx in transactions
        )

        st.subheader(i18n.t("recommendation.step3"))
        if st.button(
            i18n.t("recommendation.button_generate"),
            type="secondary",
            key="advanced_generate",
        ):
            try:
                with st.spinner(i18n.t("common.loading_recommendation")):
                    results = _generate_cached_recommendation(
                        transactions_dump,
                        responses_tuple,
                        goal,
                        locale,
                    )
            except Exception as exc:
                st.error(f"{i18n.t('errors.structuring_fail')} ({exc})")
                return

            # 保存数据到session
            st.session_state["risk_responses"] = answers
            st.session_state["investment_goal"] = goal
            risk_level_str = results.get("risk_level", "")
            if "保守" in risk_level_str or "conservative" in risk_level_str.lower():
                st.session_state["risk_profile_key"] = "conservative"
            elif "进取" in risk_level_str or "aggressive" in risk_level_str.lower():
                st.session_state["risk_profile_key"] = "aggressive"
            else:
                st.session_state["risk_profile_key"] = "balanced"

            recommendation_payload = [dict(item) for item in results["recommendations"]]
            set_product_recommendations(recommendation_payload)
            st.session_state["recommendation_explanation"] = results
            st.rerun()


if __name__ == "__main__":  # pragma: no cover - streamlit entry point
    render()
