class Order:
    def __init__(self, order_id, buyer_id, seller_id, amount):
        self.order_id = order_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.amount = amount

        self.risk_score = None
        self.decision = None  # LOW / MEDIUM / HIGH
        self.status = "CREATED"