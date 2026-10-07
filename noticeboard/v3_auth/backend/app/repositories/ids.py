from sqlalchemy import select
from sqlalchemy.orm import Session


def next_id(db: Session, model) -> str:
    """Next id for a table: its prefix plus the next value of its sequence, e.g. 'u14'."""
    return f"{model.id_prefix}{db.scalar(select(model.id_seq.next_value()))}"
