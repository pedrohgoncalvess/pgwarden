from database.operations.interface import Interface
from database.models.notifier.rule import NotifierRule


class NotifierRuleRepository(Interface[NotifierRule]):
    def __init__(self, db):
        super().__init__(NotifierRule, db)
