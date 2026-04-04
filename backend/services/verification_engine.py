class VerificationEngine:

    @staticmethod
    def get_verification_flow(decision):

        if decision == "LOW":
            return "PASSIVE"

        elif decision == "MEDIUM":
            return "USER_CONFIRMATION"

        elif decision == "HIGH":
            return "MANDATORY_VIDEO"