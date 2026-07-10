
from database.models.doc.tag import Tag


def build_tag_embedding_text(tag: Tag) -> str:
    parts = [f"Tag: {tag.name}"]
    if tag.type and tag.type != "default":
        parts.append(f"Type: {tag.type}")
    if tag.description:
        parts.append(f"Description: {tag.description}")
    return "\n".join(parts)
