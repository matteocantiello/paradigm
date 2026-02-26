"""Science domain document template and review criteria."""

from paradigm.domains.base import CriterionDef, DocumentTemplate, SectionDef

SCIENCE_TEMPLATE = DocumentTemplate(
    name="academic_paper",
    sections=[
        SectionDef(
            name="abstract",
            display_name="Abstract",
            description="Concise summary of the research question, methods, results, and conclusions.",
            assigned_roles=["writer"],
        ),
        SectionDef(
            name="introduction",
            display_name="Introduction",
            description="Background, motivation, and research question. Place work in context of existing literature.",
            assigned_roles=["writer"],
        ),
        SectionDef(
            name="methods",
            display_name="Methods",
            description="Theoretical framework, computational methods, and data analysis approach.",
            assigned_roles=["theorist"],
        ),
        SectionDef(
            name="results",
            display_name="Results",
            description="Quantitative findings from computational experiments with statistical analysis.",
            assigned_roles=["analyst"],
        ),
        SectionDef(
            name="discussion",
            display_name="Discussion",
            description="Interpretation of results, comparison to prior work, implications, and limitations.",
            assigned_roles=["synthesizer"],
        ),
        SectionDef(
            name="conclusion",
            display_name="Conclusion",
            description="Summary of key findings, main contributions, and future directions.",
            assigned_roles=["writer"],
        ),
    ],
    review_criteria=[
        CriterionDef(
            name="novelty",
            display_name="Novelty",
            description="Does the work present new ideas, methods, or findings?",
        ),
        CriterionDef(
            name="rigor",
            display_name="Rigor",
            description="Are the methods sound, the analysis correct, and the conclusions justified?",
        ),
        CriterionDef(
            name="clarity",
            display_name="Clarity",
            description="Is the paper well-written, well-organized, and easy to follow?",
        ),
        CriterionDef(
            name="significance",
            display_name="Significance",
            description="Does the work make a meaningful contribution to the field?",
        ),
    ],
    citation_style="arxiv",
    postprocessors=["latex_math"],
)

REVIEW_TEMPLATE = DocumentTemplate(
    name="literature_review",
    sections=[
        SectionDef(
            name="abstract",
            display_name="Abstract",
            description="Concise summary of the review scope, key findings, and conclusions.",
            assigned_roles=["writer"],
        ),
        SectionDef(
            name="introduction",
            display_name="Introduction",
            description=(
                "Field overview, motivation for the review, scope, "
                "and research questions addressed."
            ),
            assigned_roles=["writer"],
        ),
        SectionDef(
            name="literature_landscape",
            display_name="Literature Landscape",
            description=(
                "Overview of the field: key papers, research groups, "
                "historical development, and current state."
            ),
            assigned_roles=["synthesizer"],
        ),
        SectionDef(
            name="thematic_analysis",
            display_name="Thematic Analysis",
            description=(
                "Detailed analysis of the literature organized by theme "
                "or sub-question from the scoping phase."
            ),
            assigned_roles=["theorist"],
        ),
        SectionDef(
            name="critical_assessment",
            display_name="Critical Assessment",
            description=(
                "Methodological evaluation, identification of biases, gaps, "
                "tensions, and conflicting findings."
            ),
            assigned_roles=["skeptic"],
        ),
        SectionDef(
            name="future_directions",
            display_name="Future Directions",
            description=(
                "Open questions, promising research avenues, and recommendations for future work."
            ),
            assigned_roles=["synthesizer"],
        ),
        SectionDef(
            name="conclusion",
            display_name="Conclusion",
            description=(
                "Summary of key insights, main contributions of the review, and closing remarks."
            ),
            assigned_roles=["writer"],
        ),
    ],
    review_criteria=[
        CriterionDef(
            name="novelty",
            display_name="Novelty",
            description="Does the work present new ideas, methods, or findings?",
        ),
        CriterionDef(
            name="rigor",
            display_name="Rigor",
            description="Are the methods sound, the analysis correct, and the conclusions justified?",
        ),
        CriterionDef(
            name="clarity",
            display_name="Clarity",
            description="Is the paper well-written, well-organized, and easy to follow?",
        ),
        CriterionDef(
            name="significance",
            display_name="Significance",
            description="Does the work make a meaningful contribution to the field?",
        ),
    ],
    citation_style="numbered",
    postprocessors=["latex_math"],
)
