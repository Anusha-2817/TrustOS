class User:
    def __init__(self, user_id, role, successful_orders=0, disputes=0, fraud_flags=0):
        self.user_id = user_id
        self.role = role  # buyer / seller
        self.successful_orders = successful_orders
        self.disputes = disputes
        self.fraud_flags = fraud_flags