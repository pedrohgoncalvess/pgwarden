from database.operations.interface import Interface
from database.models.doc.tag import Tag


class TagRepository(Interface[Tag]):
    def __init__(self, db):
        super().__init__(Tag, db)
