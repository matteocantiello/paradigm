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
