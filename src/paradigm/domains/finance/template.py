"""Finance domain document template and review criteria."""

from paradigm.domains.base import CriterionDef, DocumentTemplate, SectionDef

FINANCE_TEMPLATE = DocumentTemplate(
    name="research_report",
    sections=[
        SectionDef(
            name="executive_summary",
            display_name="Executive Summary",
            description="Key findings, implications, and actionable takeaways for decision-makers.",
            assigned_roles=["writer"],
        ),
        SectionDef(
            name="background",
            display_name="Background & Context",
            description="Market context, economic environment, motivation for the research.",
            assigned_roles=["economist"],
        ),
        SectionDef(
            name="literature_review",
            display_name="Literature Review",
            description="Prior research, existing models, and knowledge gaps identified.",
            assigned_roles=["economist"],
        ),
        SectionDef(
            name="methodology",
            display_name="Methodology",
            description="Analytical framework, data sources, and models used.",
            assigned_roles=["quant"],
        ),
        SectionDef(
            name="results",
            display_name="Results",
            description="Quantitative findings, statistical outputs, and figures.",
            assigned_roles=["quant"],
        ),
        SectionDef(
            name="analysis",
            display_name="Analysis & Discussion",
            description="Interpretation of results, comparison with prior work, and limitations.",
            assigned_roles=["strategist"],
        ),
        SectionDef(
            name="risk_assessment",
            display_name="Risk Assessment",
            description="Risk factors, sensitivity analysis, and scenario modeling.",
            assigned_roles=["risk_analyst"],
        ),
        SectionDef(
            name="recommendations",
            display_name="Recommendations",
            description="Actionable conclusions, portfolio implications, and policy suggestions.",
            assigned_roles=["writer"],
        ),
    ],
    review_criteria=[
        CriterionDef(
            name="rigor",
            display_name="Analytical Rigor",
            description="Statistical methodology, data quality, and robustness checks.",
        ),
        CriterionDef(
            name="novelty",
            display_name="Novelty",
            description="New insights, models, or approaches vs existing literature.",
        ),
        CriterionDef(
            name="relevance",
            display_name="Market Relevance",
            description="Practical applicability to current market conditions.",
        ),
        CriterionDef(
            name="actionability",
            display_name="Actionability",
            description="Clear, implementable recommendations.",
        ),
        CriterionDef(
            name="risk_awareness",
            display_name="Risk Awareness",
            description="Adequate treatment of uncertainties and downside scenarios.",
        ),
    ],
    citation_style="numbered",
    postprocessors=["latex_math"],
)
