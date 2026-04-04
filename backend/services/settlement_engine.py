class SettlementEngine:

    @staticmethod
    def settle(order, decision, outcome):
        """
        outcome = SUCCESS / ISSUE / NO_RESPONSE
        """

        if decision == "LOW":
            return "ALREADY_SETTLED"

        if decision == "MEDIUM":
            if outcome == "SUCCESS":
                return "CAPTURE"
            elif outcome == "ISSUE":
                return "CANCEL"
            else:
                return "AUTO_CAPTURE"

        if decision == "HIGH":
            if outcome == "SUCCESS":
                return "RELEASE"
            elif outcome == "ISSUE":
                return "REFUND"
            else:
                return "AUTO_RELEASE"