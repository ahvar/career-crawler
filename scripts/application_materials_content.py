from __future__ import annotations

from application_materials_cover_letters import generate_cover_letter_content as _generate_cover_letter_content
from application_materials_resume import generate_resume_content, infer_skill_labels


def generate_cover_letter_content(job, context, role_family):
    return _generate_cover_letter_content(job, context, role_family, infer_skill_labels)