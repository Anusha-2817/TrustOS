class PaymentEngine:

    @staticmethod
    def process_payment(order, decision):

        if decision == "LOW":
            return {
                "type": "CAPTURE",
                "message": "Immediate payment to seller"
            }

        elif decision == "MEDIUM":
            return {
                "type": "AUTHORIZE",
                "message": "Hold payment, capture later"
            }

        elif decision == "HIGH":
            return {
                "type": "WALLET_HOLD",
                "message": "Route to wallet, no seller access"
            }