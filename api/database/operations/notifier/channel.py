from database.operations.interface import Interface
from database.models.notifier.channel import NotifierChannel


class NotifierChannelRepository(Interface[NotifierChannel]):
    def __init__(self, db):
        super().__init__(NotifierChannel, db)
