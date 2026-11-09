from django.db import models

from .deal import Deal


class ChatMessage(models.Model):
    """Small talk on the deal page. It is not part of the sealed ledger: nothing here moves
    money or changes terms. after_seq is the seq of the last ledger entry when the message was
    written, which is how the page puts it in order among the offers."""
    WHO = (("client", "client"), ("freelancer", "freelancer"))

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="chat")
    after_seq = models.IntegerField()
    who = models.CharField(max_length=12, choices=WHO)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["after_seq", "id"]
